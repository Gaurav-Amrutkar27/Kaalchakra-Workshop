/**
 * ============================================================
 * KAALCHAKRA - CORE GAME ENGINE
 * ============================================================
 *
 * Flask + MySQL version
 *
 * Features:
 *  - Dynamic chapter generation
 *  - Dynamic chapter path
 *  - Dynamic chapter titles/descriptions
 *  - Mystery Mode
 *  - Puzzle Mode
 *  - Theoretical Mode
 *  - XP / Coins / Lives
 *  - MySQL progress persistence
 *  - localStorage fallback
 *  - Chrono guide messages
 *  - Historical relic collection
 *  - Dynamic chapter unlocking
 *  - Coming-soon chapter support
 *
 * Data source:
 *  MySQL -> Flask /api/content/chapters
 *
 * chapters-data.js is NOT used by this engine.
 *
 * Flask endpoints:
 *  /api/progress/load
 *  /api/progress/save
 *
 * ============================================================
 */

(function () {

    'use strict';

    /* =========================================================
       DATABASE CONTENT
    ========================================================= */

    let databaseContent = {
        chapters: []
    };


    let contentLoaded = false;


    const CONTENT_ENDPOINT =
        '/api/content/chapters';


    /* =========================================================
       LOAD CHAPTERS FROM MYSQL THROUGH FLASK
    ========================================================= */

    async function loadChapterContent() {

        try {

            const response =
                await fetch(
                    CONTENT_ENDPOINT,
                    {
                        method: 'GET',
                        credentials: 'include',
                        cache: 'no-store',
                        headers: {
                            'Accept':
                                'application/json'
                        }
                    }
                );


            if (!response.ok) {

                throw new Error(
                    `Chapter API returned ${response.status}`
                );

            }


            const data =
                await response.json();


            if (
                !data.success ||
                !Array.isArray(data.chapters)
            ) {

                throw new Error(
                    data.message ||
                    'Invalid chapter response'
                );

            }


            databaseContent = {

                chapters:
                    data.chapters

            };


            contentLoaded = true;


            console.log(
                `KaalChakra: Loaded ${data.chapters.length} chapters from MySQL`
            );


            return databaseContent;


        } catch (error) {

            console.error(
                'Could not load chapters from MySQL:',
                error
            );


            showContentError(
                'Unable to load historical chapters. Please refresh the page.'
            );


            throw error;

        }

    }


    /* =========================================================
       CHAPTER ACCESS
    ========================================================= */

    function getChapters() {

        return databaseContent.chapters || [];

    }


    function getChapter(chapterId) {

        return getChapters().find(
            chapter =>
                Number(chapter.id) ===
                Number(chapterId)
        ) || null;

    }


    function getTopic(
        chapter,
        topicId
    ) {

        if (
            !chapter ||
            !Array.isArray(
                chapter.topics
            )
        ) {

            return null;

        }


        return chapter.topics.find(
            topic =>
                Number(topic.id) ===
                Number(topicId)
        ) || null;

    }


    function getTheoreticalData(
        topic
    ) {

        if (!topic) {
            return null;
        }


        return (
            topic.theoretical ||
            topic.info ||
            null
        );

    }


    function getModeData(
        topic,
        modeName
    ) {

        if (!topic) {
            return null;
        }


        if (
            modeName === 'theoretical' ||
            modeName === 'info'
        ) {

            return getTheoreticalData(
                topic
            );

        }


        return topic[modeName] || null;

    }


    function getModeKey(
        topicId,
        modeName
    ) {

        const normalizedMode =
            (
                modeName === 'info' ||
                modeName === 'theoretical'
            )
                ? 'theoretical'
                : modeName;


        return (
            `${topicId}_${normalizedMode}`
        );

    }


    /* =========================================================
       CONFIGURATION
    ========================================================= */

    const SAVE_KEY = 'kaalchakra_save_v3';
    const MAX_RELEASED_CHAPTERS = 5;

    const LOAD_ENDPOINT = '/api/progress/load';
    const SAVE_ENDPOINT = '/api/progress/save';


    /* =========================================================
       GAME STATE
    ========================================================= */

    let gameState = {
        xp: 120,
        coins: 25,
        score: 0,
        lives: 5,
        currentChapter: 1,
        completedModes: {},
        collectedRelics: []
    };


    let saveQueue = Promise.resolve();


    /* =========================================================
       ACTIVE GAME VARIABLES
    ========================================================= */

    let activeChapterId = 1;
    let activeTopicId = null;
    let activeMode = null;

    let puzzleUserSelection = null;

    let selectedMatchLeft = null;
    let matchingPairsState = {};


    /* =========================================================
       STATE NORMALIZATION
    ========================================================= */

    function normalizeGameState() {

        if (!gameState || typeof gameState !== 'object') {
            gameState = {};
        }


        if (typeof gameState.xp !== 'number') {
            gameState.xp = 120;
        }

        if (typeof gameState.coins !== 'number') {
            gameState.coins = 25;
        }

        if (typeof gameState.lives !== 'number') {
            gameState.lives = 5;
        }

        if (typeof gameState.currentChapter !== 'number') {
            gameState.currentChapter = 1;
        }


        if (
            !gameState.completedModes ||
            typeof gameState.completedModes !== 'object'
        ) {
            gameState.completedModes = {};
        }


        if (!Array.isArray(gameState.collectedRelics)) {
            gameState.collectedRelics = [];
        }


        const chapters = getChapters();

        if (chapters.length === 0) {
            gameState.currentChapter = 1;
            return;
        }


        if (gameState.currentChapter < 1) {
            gameState.currentChapter = 1;
        }


        if (gameState.currentChapter > chapters.length) {
            gameState.currentChapter = chapters.length;
        }
    }


    /* =========================================================
       LOAD PLAYER STATE
    ========================================================= */

    async function loadState() {

        try {

            const response = await fetch(
                LOAD_ENDPOINT,
                {
                    method: 'GET',
                    credentials: 'include',
                    cache: 'no-store'
                }
            );


            if (!response.ok) {
                throw new Error(
                    `Progress API returned ${response.status}`
                );
            }


            const data = await response.json();


            if (!data.success || !data.progress) {
                throw new Error(
                    data.message ||
                    'Invalid progress response'
                );
            }


            gameState = Object.assign(
                gameState,
                data.progress
            );

            // MySQL JSON columns may arrive as JSON strings. Keep the legacy
            // engine compatible with the same server progress used by the
            // new stage controller.
            if (typeof gameState.completedModes === 'string') {
                try {
                    gameState.completedModes = JSON.parse(gameState.completedModes || '{}') || {};
                } catch (e) {
                    gameState.completedModes = {};
                }
            }

            if (!Number.isFinite(Number(gameState.score))) {
                gameState.score = Number(data.progress.score) || 0;
            }

            normalizeGameState();


            /* ---------------------------------------------
               Local fallback cache
            --------------------------------------------- */

            try {

                localStorage.setItem(
                    SAVE_KEY,
                    JSON.stringify(gameState)
                );

            } catch (error) {

                console.warn(
                    'Could not update local progress cache:',
                    error
                );

            }


        } catch (error) {

            console.warn(
                'Could not load server progress. Using local fallback:',
                error
            );


            /* ---------------------------------------------
               Local fallback
            --------------------------------------------- */

            try {

                const saved =
                    localStorage.getItem(SAVE_KEY);


                if (saved) {

                    gameState = Object.assign(
                        gameState,
                        JSON.parse(saved)
                    );
                    if (typeof gameState.completedModes === 'string') {
                        try { gameState.completedModes = JSON.parse(gameState.completedModes || '{}') || {}; }
                        catch (e) { gameState.completedModes = {}; }
                    }
                    normalizeGameState();
                }


            } catch (localError) {

                console.warn(
                    'Could not load local fallback state:',
                    localError
                );

            }

        }


        updateHUD();
    }


    /* =========================================================
       SAVE PLAYER STATE
    ========================================================= */

    function saveState() {

        normalizeGameState();

        updateHUD();


        /* ---------------------------------------------
           Local cache
        --------------------------------------------- */

        try {

            localStorage.setItem(
                SAVE_KEY,
                JSON.stringify(gameState)
            );

        } catch (error) {

            console.warn(
                'Could not save local progress cache:',
                error
            );

        }


        /* ---------------------------------------------
           Server persistence
        --------------------------------------------- */
        /*
         * The dashboard has one authoritative progress API:
         * /api/game/complete and /api/game/hint.
         *
         * The old game engine used to POST its local gameState here. That
         * could overwrite freshly awarded XP/coins/completion state with a
         * stale copy after a mode was completed. Keep this function as a
         * compatibility no-op for callers inside the legacy game code.
         */
        return Promise.resolve();

    }


    /* =========================================================
       HUD
    ========================================================= */

    function updateHUD() {

        const xpEl =
            document.getElementById('xp');

        const coinsEl =
            document.getElementById('coins');

        const scoreEl =
            document.getElementById('score');

        const livesEl =
            document.getElementById('lives');


        if (xpEl) {
            xpEl.innerText = gameState.xp;
        }


        if (coinsEl) {
            coinsEl.innerText = gameState.coins;
        }

        if (scoreEl) {
            scoreEl.innerText = gameState.score || 0;
        }


        if (livesEl) {
            livesEl.innerText = gameState.lives;
        }

    }


    /* =========================================================
       REWARDS
    ========================================================= */

    function addRewards(reward) {
        /*
         * Rewards are now awarded exactly once by /api/game/complete when
         * the learner presses Complete Stage. The legacy game engine still
         * calls addRewards() after solving a challenge, so keep the visual
         * feedback but never mutate/persist XP or coins here.
         */
        if (!reward) return;
        triggerScreenFlash();
    }


    /* =========================================================
       SCREEN FLASH
    ========================================================= */

    function triggerScreenFlash() {

        const flash =
            document.getElementById('screenFlash');


        if (!flash) {
            return;
        }


        flash.classList.remove('flash');


        void flash.offsetWidth;


        flash.classList.add('flash');
    }


    /* =========================================================
       CHAPTER PROGRESS
    ========================================================= */

    function getChapterProgress(chapter) {

        if (
            !chapter ||
            !Array.isArray(chapter.topics) ||
            chapter.topics.length === 0
        ) {
            return 0;
        }


        const totalModes =
            chapter.topics.length * 3;


        let completed = 0;


        chapter.topics.forEach(topic => {

            if (
                gameState.completedModes[
                    getModeKey(topic.id, 'mystery')
                ]
            ) {
                completed++;
            }


            if (
                gameState.completedModes[
                    getModeKey(topic.id, 'puzzle')
                ]
            ) {
                completed++;
            }


            if (
                gameState.completedModes[
                    getModeKey(topic.id, 'theoretical')
                ]
            ) {
                completed++;
            }

        });


        return Math.round(
            (completed / totalModes) * 100
        );
    }


    /* =========================================================
       CHAPTER STATUS HELPERS
    ========================================================= */

    function isComingSoon(chapter) {

        if (!chapter) {
            return false;
        }


        return (
            chapter.comingSoon === true ||

            chapter.isComingSoon === true ||

            chapter.status === 'coming-soon' ||

            chapter.status === 'COMING_SOON'
        );
    }


    function isChapterEnded(chapter) {

        if (!chapter) {
            return false;
        }


        return (
            chapter.status === 'ended' ||
            chapter.status === 'ENDED'
        );
    }


    /* =========================================================
       CHAPTER UNLOCK
    ========================================================= */

    function isChapterUnlocked(chapterId) {

        const chapters = getChapters();


        const index =
            chapters.findIndex(
                chapter =>
                    chapter.id === chapterId
            );


        if (index < 0) {
            return false;
        }


        const chapter = chapters[index];


        /* Chapters 6 onward are intentionally sealed for the current release. */
        if (index >= MAX_RELEASED_CHAPTERS) {
            return false;
        }


        /* Coming-soon chapters cannot be opened. */

        if (isComingSoon(chapter)) {
            return false;
        }


        if (isChapterEnded(chapter)) {
            return false;
        }


        /* First chapter is always unlocked. */

        if (index === 0) {
            return true;
        }


        /*
         * currentChapter is stored as the
         * 1-based chapter number.
         */

        if (
            gameState.currentChapter >=
            index + 1
        ) {
            return true;
        }


        /*
         * Also allow access if the previous
         * chapter has started.
         */

        const previousChapter =
            chapters[index - 1];


        return (
            getChapterProgress(
                previousChapter
            ) > 0
        );
    }


    /* =========================================================
       UPDATE CHAPTER UNLOCK
    ========================================================= */

    function updateChapterUnlock(chapterId) {

        const chapters = getChapters();


        const index =
            chapters.findIndex(
                chapter =>
                    chapter.id === chapterId
            );


        if (index < 0) {
            return;
        }


        const chapter = chapters[index];


        if (
            getChapterProgress(chapter) <
            100
        ) {
            return;
        }


        /*
         * Unlock the next available chapter.
         */

        const nextIndex = index + 1;


        if (nextIndex < chapters.length) {

            const nextChapter =
                chapters[nextIndex];


            if (!isComingSoon(nextChapter)) {

                gameState.currentChapter =
                    Math.max(
                        gameState.currentChapter,
                        nextIndex + 1
                    );

            }

        }


        saveState();
    }


    /* =========================================================
       DYNAMIC ADVENTURE MAP
    ========================================================= */

    function renderAdventureMap() {

    const mapContainer =
        document.querySelector(
            '.adventure-map'
        );


    if (!mapContainer) {
        return;
    }


    const chapters =
        getChapters();


    if (!chapters.length) {

        mapContainer.innerHTML = `

            <div
                class="text-center p-5"
                style="
                    color:#ffd45e;
                "
            >
                📜 No chapters are currently available.
            </div>

        `;

        return;
    }


    let html = '';

    html += `
        <div
            class="journey-road"
            id="journeyRoad"
        ></div>
    `;


    chapters.forEach(
        (chapter, index) => {

            const progress =
                getChapterProgress(
                    chapter
                );


            const comingSoon =
                index >= MAX_RELEASED_CHAPTERS ||
                chapter.status === 'COMING_SOON';


            const ended =
                chapter.status ===
                'ENDED';


            const unlocked =
                isChapterUnlocked(
                    chapter.id
                );


            let statusLabel =
                'MISSION START';


            if (comingSoon) {

                statusLabel =
                    'COMING SOON';

            } else if (ended) {

                statusLabel =
                    'CHAPTER ENDED';

            } else if (
                progress === 100
            ) {

                statusLabel =
                    'COMPLETED ⭐';

            } else if (!unlocked) {

                statusLabel =
                    'LOCKED';

            } else if (
                progress > 0
            ) {

                statusLabel =
                    'IN PROGRESS';

            }


            const description =
                chapter.description ||
                'Historical quest';


            const disabled =
                comingSoon ||
                ended;


            const isRight =
                index % 2 === 1;


            const cardHTML = `

                <div
                    class="
                        chapter-card
                        ${
                            isRight
                                ? 'right-card'
                                : 'left-card'
                        }
                    "
                    data-chapter-id="${chapter.id}"
                    data-coming-soon="${
                        comingSoon
                            ? 'true'
                            : 'false'
                    }"
                    data-status="${
                        chapter.status
                    }"
                    style="
                        ${
                            disabled
                                ? `
                                    opacity:0.6;
                                    filter:grayscale(0.45);
                                  `
                                : ''
                        }
                    "
                    ${
                        disabled
                            ? ''
                            : `
                                onclick="
                                    KaalchakraEngine.openChapter(
                                        ${chapter.id}
                                    )
                                "
                              `
                    }
                >

                    <span
                        class="chapter-number"
                    >
                        ${
                            chapter.number ||
                            index + 1
                        }
                    </span>


                    <span
                        class="chapter-icon"
                    >
                        ${
                            chapter.icon ||
                            '📜'
                        }
                    </span>


                    <div
                        class="chapter-title"
                    >
                        ${chapter.title}
                    </div>


                    <div
                        class="chapter-subtitle"
                    >
                        ${description}
                    </div>


                    <div
                        class="progress-label"
                    >

                        <span>
                            ${statusLabel}
                        </span>

                        <span>
                            ${progress}%
                        </span>

                    </div>


                    <div
                        class="progress"
                    >

                        <div
                            class="progress-bar"
                            style="
                                width:${progress}%;
                            "
                        ></div>

                    </div>

                </div>

            `;


            const portalHTML = `

                <div
                    class="chapter-portal"
                    ${
                        disabled
                            ? ''
                            : `
                                onclick="
                                    KaalchakraEngine.openChapter(
                                        ${chapter.id}
                                    )
                                "
                              `
                    }
                    title="${chapter.title}"
                    style="
                        ${
                            disabled
                                ? `
                                    opacity:0.5;
                                    cursor:not-allowed;
                                  `
                                : ''
                        }
                    "
                >
                    ${
                        chapter.portalIcon ||
                        chapter.icon ||
                        '📜'
                    }
                </div>

            `;


            if (isRight) {

                html += `

                    <div
                        class="chapter-row"
                        id="
                            chapter-row-${chapter.id}
                        "
                    >

                        <div></div>

                        ${portalHTML}

                        ${cardHTML}

                    </div>

                `;

            } else {

                html += `

                    <div
                        class="chapter-row"
                        id="
                            chapter-row-${chapter.id}
                        "
                    >

                        ${cardHTML}

                        ${portalHTML}

                        <div></div>

                    </div>

                `;

            }

        }
    );


    html += `

        <div
            class="player"
            id="playerToken"
        >

            <div
                class="player-character"
            >
                🧑‍🚀
            </div>

            <div
                class="player-name"
            >
                YOU
            </div>

        </div>

    `;


    mapContainer.innerHTML =
        html;


    adjustJourneyRoadHeight();

    positionPlayerToken();


    document.dispatchEvent(
        new CustomEvent(
            'kaalchakra:chapters-rendered',
            {
                detail: {
                    chapters:
                        chapters
                }
            }
        )
    );

}


    /* =========================================================
       DYNAMIC ROAD HEIGHT
    ========================================================= */

    function adjustJourneyRoadHeight() {

        const road =
            document.getElementById(
                'journeyRoad'
            );


        const rows =
            document.querySelectorAll(
                '.chapter-row'
            );


        if (
            !road ||
            rows.length === 0
        ) {
            return;
        }


        const firstRow =
            rows[0];


        const lastRow =
            rows[rows.length - 1];


        const topOffset =
            firstRow.offsetTop + 40;


        const bottomOffset =
            lastRow.offsetTop +
            lastRow.offsetHeight -
            60;


        road.style.top =
            topOffset + 'px';


        road.style.height =
            Math.max(
                300,
                bottomOffset -
                topOffset
            ) + 'px';
    }


    /* =========================================================
       PLAYER TOKEN POSITION
    ========================================================= */

    function positionPlayerToken() {

        const token =
            document.getElementById(
                'playerToken'
            );


        if (!token) {
            return;
        }


        const chapters =
            getChapters();


        if (!chapters.length) {
            return;
        }


        let targetChapterId =
            chapters[0].id;


        for (
            const chapter of chapters
        ) {

            if (
                isComingSoon(chapter) ||
                isChapterEnded(chapter)
            ) {
                continue;
            }


            if (
                getChapterProgress(chapter) <
                100
            ) {

                targetChapterId =
                    chapter.id;

                break;
            }


            targetChapterId =
                chapter.id;
        }


        const targetRow =
            document.getElementById(
                `chapter-row-${targetChapterId}`
            );


        if (targetRow) {

            token.style.top =
                (
                    targetRow.offsetTop +
                    targetRow.offsetHeight -
                    55
                ) + 'px';

        }
    }


    /* =========================================================
       OPEN CHAPTER
    ========================================================= */

    function openChapter(chapterId) {

        const chapter =
            getChapter(chapterId);


        if (!chapter) {
            return;
        }


        if (isComingSoon(chapter)) {

            setChronoMessage(
                'This chapter is coming soon. New historical adventures will be added to your journey!'
            );

            return;
        }


        if (isChapterEnded(chapter)) {

            setChronoMessage(
                'This chapter has ended. Continue exploring the available historical journey!'
            );

            return;
        }


        if (!isChapterUnlocked(chapterId)) {

            setChronoMessage(
                'This chapter is still locked. Complete more of the previous chapter to unlock it!'
            );

            return;
        }


        activeChapterId =
            chapterId;


        activeTopicId =
            chapter.topics &&
            chapter.topics.length
                ? chapter.topics[0].id
                : null;


        activeMode = null;


        puzzleUserSelection = null;


        selectedMatchLeft = null;


        matchingPairsState = {};


        renderChapterModal();


        const modalEl =
            document.getElementById(
                'chapterModal'
            );


        if (
            modalEl &&
            typeof bootstrap !== 'undefined'
        ) {

            const bsModal =
                bootstrap.Modal.getOrCreateInstance(
                    modalEl
                );


            bsModal.show();
        }


        showChapterChronoMessage(
            chapter
        );
    }


    /* =========================================================
       CHRONO CHAPTER MESSAGES
    ========================================================= */

    function showChapterChronoMessage(
        chapter
    ) {

        const messages = {

            1:
                'Welcome to Chapter 1! Follow the earliest people and uncover how they lived, hunted, gathered and survived.',

            2:
                'A new way of life begins! Discover how humans learned to grow food and domesticate animals.',

            3:
                'An ancient civilisation awaits! Explore the earliest cities, streets, drains, crafts and trade.',

            4:
                'Become a history detective! Ancient books, burials and artefacts reveal clues about the past.',

            5:
                'Enter the age of Ashoka! Discover the Mauryan Empire and the emperor who gave up war.',

            6:
                'History detective mode activated! Learn how historians reconstruct the past from different sources.',

            7:
                'New questions changed ancient India. Explore Buddhism, Jainism and new ideas about life.',

            8:
                'Villages and towns are growing! Explore farming, iron technology, crafts and ancient trade.',

            9:
                'Great kingdoms and empires rise. Discover powerful rulers and changing political landscapes.',

            10:
                'Marvel at ancient masterpieces, literature, science, mathematics and extraordinary architecture.'

        };


        const number =
            chapter.number ||
            chapter.id;


        const message =
            messages[number] ||
            `Exploring Chapter ${number}: ${chapter.title}!`;


        setChronoMessage(
            message
        );
    }


    /* =========================================================
       CHAPTER MODAL
    ========================================================= */

    function renderChapterModal() {

        const modalTitle =
            document.getElementById(
                'modalTitle'
            );


        const modalBody =
            document.querySelector(
                '#chapterModal .modal-body'
            );


        if (
            !modalTitle ||
            !modalBody
        ) {
            return;
        }


        const chapter =
            getChapter(
                activeChapterId
            );


        if (!chapter) {
            return;
        }


        modalTitle.innerHTML =
            `CHAPTER ${chapter.number} — ${chapter.title}`;


        if (!activeMode) {

            renderTopicSelectView(
                chapter,
                modalBody
            );

        } else if (
            activeMode === 'mystery'
        ) {

            renderMysteryGameView(
                chapter,
                modalBody
            );

        } else if (
            activeMode === 'puzzle'
        ) {

            renderPuzzleGameView(
                chapter,
                modalBody
            );

        } else if (
            activeMode === 'theoretical' ||
            activeMode === 'info'
        ) {

            renderTheoreticalView(
                chapter,
                modalBody
            );

        }
    }


    /* =========================================================
       TOPIC SELECT VIEW
    ========================================================= */

    function renderTopicSelectView(
        chapter,
        container
    ) {

        if (
            !Array.isArray(
                chapter.topics
            ) ||
            chapter.topics.length === 0
        ) {

            container.innerHTML = `

                <div class="text-center p-4">

                    <div style="font-size:40px;">
                        📜
                    </div>

                    <h5 style="color:#ffd45e;">
                        Chapter Content Coming Soon
                    </h5>

                    <p style="color:#c4b9a0;">
                        The games for this chapter
                        are currently being prepared.
                    </p>

                </div>

            `;

            return;
        }


        const currentTopic =
            getTopic(
                chapter,
                activeTopicId
            ) ||
            chapter.topics[0];


        activeTopicId =
            currentTopic.id;


        /* ---------------------------------------------
           Topic navigation
        --------------------------------------------- */

        let topicsNavHTML = `

            <div
                class="topic-nav-tabs
                       d-flex
                       gap-2
                       mb-3
                       flex-wrap
                       justify-content-center"
            >

        `;


        chapter.topics.forEach(
            (topic, index) => {

                const isActive =
                    topic.id ===
                    activeTopicId;


                topicsNavHTML += `

                    <button
                        type="button"
                        class="
                            btn
                            btn-sm
                            ${
                                isActive
                                    ? 'btn-warning text-dark font-weight-bold'
                                    : 'btn-outline-warning text-light'
                            }
                        "
                        style="
                            border-radius:20px;
                            font-weight:bold;
                            font-size:12px;
                            padding:6px 14px;
                        "
                        onclick="
                            KaalchakraEngine.selectTopic('${topic.id}')
                        "
                    >
                        ${topic.icon || '📜'}
                        Topic ${index + 1}
                    </button>

                `;

            }
        );


        topicsNavHTML += `
            </div>
        `;


        /* ---------------------------------------------
           Mode completion
        --------------------------------------------- */

        const mysteryDone =
            gameState.completedModes[
                getModeKey(
                    currentTopic.id,
                    'mystery'
                )
            ];


        const puzzleDone =
            gameState.completedModes[
                getModeKey(
                    currentTopic.id,
                    'puzzle'
                )
            ];


        const theoreticalDone =
            gameState.completedModes[
                getModeKey(
                    currentTopic.id,
                    'theoretical'
                )
            ];


        const theoreticalData =
            getTheoreticalData(
                currentTopic
            );


        container.innerHTML = `

            <div class="text-center mb-2">

                <span
                    class="
                        badge
                        bg-warning
                        text-dark
                        px-3
                        py-1
                        mb-2
                    "
                    style="
                        font-size:11px;
                        letter-spacing:2px;
                    "
                >
                    ✦
                    ${(chapter.era || 'HISTORY').toUpperCase()}
                    ✦
                </span>


                <p
                    style="
                        font-size:13px;
                        color:#d8cdb9;
                        margin-bottom:12px;
                        line-height:1.5;
                    "
                >
                    ${
                        chapter.description ||
                        chapter.subtitle ||
                        ''
                    }
                </p>

            </div>


            ${topicsNavHTML}


            <div
                class="topic-card p-3 mb-3"
                style="
                    background:rgba(255,255,255,0.05);
                    border:1px solid rgba(244,191,72,0.3);
                    border-radius:16px;
                "
            >

                <div
                    class="
                        d-flex
                        align-items-center
                        gap-2
                        mb-1
                    "
                >

                    <span
                        style="font-size:24px;"
                    >
                        ${currentTopic.icon || '📜'}
                    </span>


                    <h6
                        style="
                            color:#ffd45e;
                            margin:0;
                            font-weight:bold;
                            font-size:15px;
                        "
                    >
                        ${currentTopic.title}
                    </h6>

                </div>


                <p
                    style="
                        font-size:12px;
                        color:#c4b9a0;
                        margin:6px 0 12px 0;
                    "
                >
                    ${currentTopic.summary || ''}
                </p>


                <div
                    class="text-center mb-2"
                >

                    <span
                        style="
                            font-size:11px;
                            color:#ffd764;
                            letter-spacing:1px;
                            font-weight:bold;
                        "
                    >
                        SELECT A GAME MODE TO PLAY
                    </span>

                </div>


                <div
                    class="d-grid gap-2"
                >

                    <!-- MYSTERY -->

                    <button
                        class="
                            mode-select-btn
                            d-flex
                            align-items-center
                            justify-content-between
                            p-2
                            px-3
                        "
                        style="
                            background:
                                linear-gradient(
                                    135deg,
                                    #2b1f14,
                                    #1b161f
                                );
                            border:
                                1px solid #dcae4e;
                            border-radius:12px;
                            color:#ffe69a;
                            cursor:pointer;
                            transition:0.25s;
                        "
                        onclick="
                            KaalchakraEngine.launchMode('mystery')
                        "
                    >

                        <div class="text-start">

                            <div
                                style="
                                    font-weight:bold;
                                    font-size:13px;
                                "
                            >
                                🕵️ MYSTERY MODE
                            </div>

                            <small
                                style="
                                    color:#bdae90;
                                    font-size:11px;
                                "
                            >
                                Investigate clues
                                & solve the historical case
                            </small>

                        </div>


                        <span
                            class="
                                badge
                                ${
                                    mysteryDone
                                        ? 'bg-success'
                                        : 'bg-warning text-dark'
                                }
                            "
                        >
                            ${
                                mysteryDone
                                    ? '⭐ DONE'
                                    : '+40 XP'
                            }
                        </span>

                    </button>


                    <!-- PUZZLE -->

                    <button
                        class="
                            mode-select-btn
                            d-flex
                            align-items-center
                            justify-content-between
                            p-2
                            px-3
                        "
                        style="
                            background:
                                linear-gradient(
                                    135deg,
                                    #182329,
                                    #12191e
                                );
                            border:
                                1px solid #5aa5bd;
                            border-radius:12px;
                            color:#c6eaf5;
                            cursor:pointer;
                            transition:0.25s;
                        "
                        onclick="
                            KaalchakraEngine.launchMode('puzzle')
                        "
                    >

                        <div class="text-start">

                            <div
                                style="
                                    font-weight:bold;
                                    font-size:13px;
                                "
                            >
                                🧩 PUZZLE MODE
                            </div>

                            <small
                                style="
                                    color:#9cbcc7;
                                    font-size:11px;
                                "
                            >
                                Interactive historical puzzles
                            </small>

                        </div>


                        <span
                            class="
                                badge
                                ${
                                    puzzleDone
                                        ? 'bg-success'
                                        : 'bg-info text-dark'
                                }
                            "
                        >
                            ${
                                puzzleDone
                                    ? '⭐ DONE'
                                    : '+35 XP'
                            }
                        </span>

                    </button>


                    <!-- THEORETICAL -->

                    <button
                        class="
                            mode-select-btn
                            d-flex
                            align-items-center
                            justify-content-between
                            p-2
                            px-3
                        "
                        style="
                            background:
                                linear-gradient(
                                    135deg,
                                    #222616,
                                    #141810
                                );
                            border:
                                1px solid #84a849;
                            border-radius:12px;
                            color:#e4f5c6;
                            cursor:pointer;
                            transition:0.25s;
                        "
                        onclick="
                            KaalchakraEngine.launchMode('theoretical')
                        "
                    >

                        <div class="text-start">

                            <div
                                style="
                                    font-weight:bold;
                                    font-size:13px;
                                "
                            >
                                📖 THEORETICAL MODE
                            </div>

                            <small
                                style="
                                    color:#b5c79e;
                                    font-size:11px;
                                "
                            >
                                Learn concepts and answer
                                knowledge questions
                            </small>

                        </div>


                        <span
                            class="
                                badge
                                ${
                                    theoreticalDone
                                        ? 'bg-success'
                                        : 'bg-success-subtle text-light'
                                }
                            "
                        >
                            ${
                                theoreticalDone
                                    ? '⭐ DONE'
                                    : '+20 XP'
                            }
                        </span>

                    </button>

                </div>

            </div>

        `;

    }


    /* =========================================================
       MYSTERY MODE
    ========================================================= */

    function renderMysteryGameView(
        chapter,
        container
    ) {

        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const mystery =
            getModeData(
                topic,
                'mystery'
            );


        if (!mystery) {

            container.innerHTML = `
                <div class="alert alert-warning">
                    Mystery content is not available for this topic yet.
                </div>
            `;

            return;
        }


        const isDone =
            gameState.completedModes[
                getModeKey(
                    topic.id,
                    'mystery'
                )
            ];


        let cluesHTML = '';


        (mystery.clues || []).forEach(
            clue => {

                cluesHTML += `

                    <div
                        class="clue-card p-2 px-3 mb-2"
                        style="
                            background:
                                rgba(220,174,78,0.1);
                            border-left:
                                4px solid #ffd45d;
                            border-radius:8px;
                        "
                    >

                        <div
                            style="
                                font-size:11px;
                                font-weight:bold;
                                color:#ffd764;
                            "
                        >
                            🔍 ${clue.label || 'CLUE'}
                        </div>


                        <div
                            style="
                                font-size:12px;
                                color:#f0e6d2;
                                margin-top:2px;
                            "
                        >
                            ${clue.text || ''}
                        </div>

                    </div>

                `;

            }
        );


        let optionsHTML = '';


        (mystery.options || []).forEach(
            (option, index) => {

                optionsHTML += `

                    <button
                        type="button"
                        class="
                            btn
                            btn-outline-warning
                            text-start
                            mb-2
                            w-100
                            mystery-opt-btn
                        "
                        style="
                            border-radius:10px;
                            font-size:13px;
                            padding:10px 14px;
                            background:
                                rgba(0,0,0,0.3);
                        "
                        onclick="
                            KaalchakraEngine.checkMysteryAnswer(${index})
                        "
                    >

                        <span
                            style="
                                font-weight:bold;
                                margin-right:6px;
                            "
                        >
                            ${String.fromCharCode(65 + index)}.
                        </span>

                        ${option}

                    </button>

                `;

            }
        );


        container.innerHTML = `

            <div
                class="
                    d-flex
                    justify-content-between
                    align-items-center
                    mb-3
                "
            >

                <button
                    class="
                        btn
                        btn-sm
                        btn-outline-secondary
                        text-light
                    "
                    onclick="
                        KaalchakraEngine.backToTopics()
                    "
                    style="
                        border-radius:20px;
                        font-size:11px;
                    "
                >
                    ← Back to Topics
                </button>


                <span
                    class="badge bg-warning text-dark"
                >
                    🕵️ MYSTERY INVESTIGATION
                </span>

            </div>


            <div
                class="mystery-briefing p-3 mb-3"
                style="
                    background:
                        rgba(0,0,0,0.4);
                    border:
                        1px solid rgba(244,191,72,0.3);
                    border-radius:14px;
                "
            >

                <h6
                    style="
                        color:#ffd45e;
                        font-weight:bold;
                        font-size:15px;
                        margin-bottom:6px;
                    "
                >
                    🔎 ${mystery.title}
                </h6>


                <p
                    style="
                        font-size:12px;
                        color:#ddd2be;
                        line-height:1.6;
                        margin-bottom:12px;
                    "
                >
                    ${mystery.scenario || ''}
                </p>


                <div
                    class="mb-2"
                    style="
                        font-size:11px;
                        font-weight:bold;
                        color:#ffd764;
                        letter-spacing:1px;
                    "
                >
                    EVIDENCE COLLECTED:
                </div>


                ${cluesHTML}

            </div>


            <div
                class="p-3 mb-2"
                style="
                    background:
                        rgba(255,255,255,0.03);
                    border:
                        1px solid rgba(255,255,255,0.1);
                    border-radius:14px;
                "
            >

                <div
                    class="mb-2"
                    style="
                        color:#ffe69a;
                        font-weight:bold;
                        font-size:13px;
                    "
                >
                    ❓ DETECTIVE DEDUCTION:
                    ${mystery.question || ''}
                </div>


                <div id="mysteryOptionsContainer">
                    ${optionsHTML}
                </div>


                <div
                    id="mysteryFeedback"
                    class="mt-3"
                    style="display:none;"
                ></div>

            </div>

        `;


        if (isDone) {

            showMysteryFeedback(
                true,
                mystery.explanation ||
                    'Case already solved.',
                true
            );

        }

    }


    /* =========================================================
       CHECK MYSTERY
    ========================================================= */

    function checkMysteryAnswer(
        selectedIndex
    ) {

        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const mystery =
            getModeData(
                topic,
                'mystery'
            );


        if (!mystery) {
            return;
        }


        if (
            selectedIndex ===
            mystery.correct
        ) {

            const modeKey =
                getModeKey(
                    topic.id,
                    'mystery'
                );


            const isFirstTime =
                !gameState.completedModes[
                    modeKey
                ];


            gameState.completedModes[
                modeKey
            ] = true;


            updateChapterUnlock(
                activeChapterId
            );


            if (isFirstTime) {

                addRewards(
                    mystery.reward
                );


                const rewardXP =
                    mystery.reward?.xp || 0;


                const rewardCoins =
                    mystery.reward?.coins || 0;


                setChronoMessage(
                    `Brilliant deduction, Detective! You solved the case: ${mystery.title}. +${rewardXP} XP and +${rewardCoins} coins!`
                );

            }


            showMysteryFeedback(
                true,
                mystery.explanation ||
                    'Excellent deduction!',
                false
            );


            renderAdventureMap();

        } else {

            showMysteryFeedback(
                false,
                'Not quite right, Detective! Re-examine the collected evidence and try another option.'
            );

        }

    }


    /* =========================================================
       MYSTERY FEEDBACK
    ========================================================= */

    function showMysteryFeedback(
        isCorrect,
        explanationText,
        isReview
    ) {

        const feedbackEl =
            document.getElementById(
                'mysteryFeedback'
            );


        if (!feedbackEl) {
            return;
        }


        feedbackEl.style.display =
            'block';


        if (isCorrect) {

            feedbackEl.className =
                'p-3 rounded alert alert-success text-dark';


            feedbackEl.innerHTML = `

                <div
                    style="
                        font-weight:bold;
                        font-size:14px;
                        margin-bottom:4px;
                    "
                >
                    🎉 CASE SOLVED!

                    ${
                        isReview
                            ? '(Already Completed)'
                            : ''
                    }
                </div>


                <div
                    style="
                        font-size:12px;
                        line-height:1.5;
                    "
                >
                    ${explanationText}
                </div>

            `;

        } else {

            feedbackEl.className =
                'p-3 rounded alert alert-danger text-dark';


            feedbackEl.innerHTML = `

                <div
                    style="
                        font-weight:bold;
                        font-size:13px;
                    "
                >
                    ❌ Clue mismatch!
                </div>


                <div
                    style="
                        font-size:12px;
                    "
                >
                    ${explanationText}
                </div>

            `;

        }

    }


    /* =========================================================
       PUZZLE MODE
    ========================================================= */

    function renderPuzzleGameView(
        chapter,
        container
    ) {

        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const puzzle =
            getModeData(
                topic,
                'puzzle'
            );


        if (!puzzle) {

            container.innerHTML = `
                <div class="alert alert-warning">
                    Puzzle content is not available for this topic yet.
                </div>
            `;

            return;
        }


        const isDone =
            gameState.completedModes[
                getModeKey(
                    topic.id,
                    'puzzle'
                )
            ];


        container.innerHTML = `

            <div
                class="
                    d-flex
                    justify-content-between
                    align-items-center
                    mb-3
                "
            >

                <button
                    class="
                        btn
                        btn-sm
                        btn-outline-secondary
                        text-light
                    "
                    onclick="
                        KaalchakraEngine.backToTopics()
                    "
                    style="
                        border-radius:20px;
                        font-size:11px;
                    "
                >
                    ← Back to Topics
                </button>


                <span
                    class="badge bg-info text-dark"
                >
                    🧩 PUZZLE CHALLENGE
                </span>

            </div>


            <div
                class="puzzle-box p-3 mb-3"
                style="
                    background:
                        rgba(0,0,0,0.4);
                    border:
                        1px solid rgba(90,165,189,0.4);
                    border-radius:14px;
                "
            >

                <h6
                    style="
                        color:#79cce6;
                        font-weight:bold;
                        font-size:15px;
                        margin-bottom:4px;
                    "
                >
                    🧩 ${puzzle.title}
                </h6>


                <p
                    style="
                        font-size:12px;
                        color:#d0e7ee;
                        margin-bottom:12px;
                    "
                >
                    ${puzzle.instructions || ''}
                </p>


                <div
                    id="puzzleInteractiveArea"
                ></div>


                <div
                    id="puzzleFeedback"
                    class="mt-3"
                    style="display:none;"
                ></div>

            </div>

        `;


        const area =
            document.getElementById(
                'puzzleInteractiveArea'
            );


        if (
            puzzle.type === 'sequence'
        ) {

            initSequencePuzzle(
                puzzle,
                area,
                isDone
            );

        } else if (
            puzzle.type === 'matching'
        ) {

            initMatchingPuzzle(
                puzzle,
                area,
                isDone
            );

        } else {

            renderGenericPuzzle(
                puzzle,
                area,
                isDone
            );

        }

    }


    /* =========================================================
       SEQUENCE PUZZLE
    ========================================================= */

    function initSequencePuzzle(
        puzzle,
        area,
        isDone
    ) {

        if (
            !Array.isArray(
                puzzle.items
            )
        ) {
            area.innerHTML =
                '<div class="alert alert-warning">Puzzle data is incomplete.</div>';

            return;
        }


        let order =
            puzzleUserSelection ||
            puzzle.items.map(
                item => item.id
            );


        if (
            !puzzleUserSelection &&
            !isDone
        ) {

            order =
                [...order].sort(
                    () =>
                        Math.random() -
                        0.5
                );


            puzzleUserSelection =
                order;
        }


        renderSequenceCards(
            puzzle,
            area,
            order
        );
    }


    function renderSequenceCards(
        puzzle,
        area,
        order
    ) {

        let itemsHTML = `

            <div
                class="
                    sequence-list
                    d-flex
                    flex-column
                    gap-2
                    mb-3
                "
            >

        `;


        order.forEach(
            (itemId, index) => {

                const item =
                    puzzle.items.find(
                        current =>
                            current.id ===
                            itemId
                    );


                if (!item) {
                    return;
                }


                itemsHTML += `

                    <div
                        class="
                            sequence-card
                            d-flex
                            align-items-center
                            justify-content-between
                            p-2
                            px-3
                        "
                        style="
                            background:
                                rgba(255,255,255,0.06);
                            border:
                                1px solid
                                rgba(255,213,91,0.25);
                            border-radius:10px;
                        "
                    >

                        <div
                            class="
                                d-flex
                                align-items-center
                                gap-2
                            "
                        >

                            <span
                                class="
                                    badge
                                    bg-warning
                                    text-dark
                                "
                                style="width:24px;"
                            >
                                ${index + 1}
                            </span>


                            <span
                                style="
                                    font-size:12px;
                                    color:#ffe69a;
                                "
                            >
                                ${item.text}
                            </span>

                        </div>


                        <div
                            class="d-flex gap-1"
                        >

                            <button
                                type="button"
                                class="
                                    btn
                                    btn-sm
                                    btn-dark
                                    text-warning
                                    p-1
                                    px-2
                                "
                                onclick="
                                    KaalchakraEngine.moveSequence(${index}, -1)
                                "
                                ${
                                    index === 0
                                        ? 'disabled'
                                        : ''
                                }
                            >
                                ▲
                            </button>


                            <button
                                type="button"
                                class="
                                    btn
                                    btn-sm
                                    btn-dark
                                    text-warning
                                    p-1
                                    px-2
                                "
                                onclick="
                                    KaalchakraEngine.moveSequence(${index}, 1)
                                "
                                ${
                                    index ===
                                    order.length - 1
                                        ? 'disabled'
                                        : ''
                                }
                            >
                                ▼
                            </button>

                        </div>

                    </div>

                `;

            }
        );


        itemsHTML += `
            </div>
        `;


        itemsHTML += `

            <button
                class="start-button w-100 py-2"
                onclick="
                    KaalchakraEngine.checkSequenceSolution()
                "
            >
                ✓ VERIFY TIMELINE ORDER
            </button>

        `;


        area.innerHTML =
            itemsHTML;
    }


    /* =========================================================
       MOVE SEQUENCE
    ========================================================= */

    function moveSequence(
        index,
        direction
    ) {

        if (!puzzleUserSelection) {
            return;
        }


        const newIndex =
            index + direction;


        if (
            newIndex < 0 ||
            newIndex >=
                puzzleUserSelection.length
        ) {
            return;
        }


        const temp =
            puzzleUserSelection[index];


        puzzleUserSelection[index] =
            puzzleUserSelection[newIndex];


        puzzleUserSelection[newIndex] =
            temp;


        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const area =
            document.getElementById(
                'puzzleInteractiveArea'
            );


        if (area) {

            renderSequenceCards(
                topic.puzzle,
                area,
                puzzleUserSelection
            );

        }

    }


    /* =========================================================
       CHECK SEQUENCE
    ========================================================= */

    function checkSequenceSolution() {

        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const puzzle =
            getModeData(
                topic,
                'puzzle'
            );


        if (!puzzle) {
            return;
        }


        const isCorrect =
            JSON.stringify(
                puzzleUserSelection
            ) ===
            JSON.stringify(
                puzzle.correctOrder
            );


        const feedbackEl =
            document.getElementById(
                'puzzleFeedback'
            );


        if (!feedbackEl) {
            return;
        }


        feedbackEl.style.display =
            'block';


        if (isCorrect) {

            const modeKey =
                getModeKey(
                    topic.id,
                    'puzzle'
                );


            const isFirst =
                !gameState.completedModes[
                    modeKey
                ];


            gameState.completedModes[
                modeKey
            ] = true;


            updateChapterUnlock(
                activeChapterId
            );


            if (isFirst) {

                addRewards(
                    puzzle.reward
                );


                setChronoMessage(
                    `Splendid job! Timeline puzzle complete. +${puzzle.reward?.xp || 0} XP and +${puzzle.reward?.coins || 0} coins!`
                );

            }


            feedbackEl.className =
                'p-3 rounded alert alert-success text-dark';


            feedbackEl.innerHTML = `

                <div
                    style="
                        font-weight:bold;
                        font-size:13px;
                        margin-bottom:2px;
                    "
                >
                    🎉 PERFECT CHRONOLOGICAL ORDER!
                </div>


                <div
                    style="font-size:12px;"
                >
                    ${puzzle.explanation || ''}
                </div>

            `;


            renderAdventureMap();

        } else {

            feedbackEl.className =
                'p-3 rounded alert alert-warning text-dark';


            feedbackEl.innerHTML = `

                <div
                    style="
                        font-weight:bold;
                        font-size:13px;
                    "
                >
                    Not quite the right sequence!
                </div>


                <div
                    style="font-size:12px;"
                >
                    Review the clues and
                    rearrange the timeline.
                </div>

            `;

        }

    }


    /* =========================================================
       MATCHING PUZZLE
    ========================================================= */

    function initMatchingPuzzle(
        puzzle,
        area,
        isDone
    ) {

        selectedMatchLeft = null;

        matchingPairsState = {};


        if (
            !Array.isArray(puzzle.items) ||
            !Array.isArray(puzzle.matches)
        ) {

            area.innerHTML =
                '<div class="alert alert-warning">Matching puzzle data is incomplete.</div>';

            return;
        }


        renderMatchingGrid(
            puzzle,
            area
        );
    }


    function renderMatchingGrid(
        puzzle,
        area
    ) {

        let leftHTML = `

            <div
                class="
                    col-6
                    d-flex
                    flex-column
                    gap-2
                "
            >

        `;


        puzzle.items.forEach(
            item => {

                const isMatched =
                    !!matchingPairsState[
                        item.id
                    ];


                const isSelected =
                    selectedMatchLeft ===
                    item.id;


                const background =
                    isMatched
                        ? 'rgba(76,175,80,0.2)'
                        : isSelected
                            ? 'rgba(255,215,64,0.3)'
                            : 'rgba(255,255,255,0.06)';


                const border =
                    isMatched
                        ? '#4caf50'
                        : isSelected
                            ? '#ffd54f'
                            : 'rgba(255,255,255,0.15)';


                const textColor =
                    isMatched
                        ? '#a5d6a7'
                        : '#fff';


                leftHTML += `

                    <button
                        type="button"
                        class="btn text-start p-2"
                        style="
                            border-radius:10px;
                            font-size:11px;
                            font-weight:bold;
                            background:${background};
                            border:1px solid ${border};
                            color:${textColor};
                        "
                        onclick="
                            KaalchakraEngine.selectMatchLeft('${item.id}')
                        "
                        ${
                            isMatched
                                ? 'disabled'
                                : ''
                        }
                    >

                        ${item.label || item.text}

                        ${
                            isMatched
                                ? ' ✓'
                                : ''
                        }

                    </button>

                `;

            }
        );


        leftHTML += `
            </div>
        `;


        let rightHTML = `

            <div
                class="
                    col-6
                    d-flex
                    flex-column
                    gap-2
                "
            >

        `;


        puzzle.matches.forEach(
            match => {

                const matchedLeftId =
                    Object.keys(
                        matchingPairsState
                    ).find(
                        key =>
                            matchingPairsState[key] ===
                            match.id
                    );


                const isMatched =
                    !!matchedLeftId;


                rightHTML += `

                    <button
                        type="button"
                        class="btn text-start p-2"
                        style="
                            border-radius:10px;
                            font-size:11px;
                            background:
                                ${
                                    isMatched
                                        ? 'rgba(76,175,80,0.2)'
                                        : 'rgba(255,255,255,0.06)'
                                };
                            border:
                                1px solid
                                ${
                                    isMatched
                                        ? '#4caf50'
                                        : 'rgba(255,255,255,0.15)'
                                };
                            color:
                                ${
                                    isMatched
                                        ? '#a5d6a7'
                                        : '#ddd'
                                };
                        "
                        onclick="
                            KaalchakraEngine.selectMatchRight('${match.id}')
                        "
                        ${
                            isMatched
                                ? 'disabled'
                                : ''
                        }
                    >

                        ${match.text}

                        ${
                            isMatched
                                ? ' ✓'
                                : ''
                        }

                    </button>

                `;

            }
        );


        rightHTML += `
            </div>
        `;


        area.innerHTML = `

            <div
                class="row g-2 mb-3"
            >

                ${leftHTML}

                ${rightHTML}

            </div>


            <div
                class="text-center"
                style="
                    font-size:11px;
                    color:#a4cdd9;
                "
            >
                Tap a concept on the left,
                then its matching description
                on the right.
            </div>

        `;
    }


    /* =========================================================
       MATCH LEFT
    ========================================================= */

    function selectMatchLeft(
        itemId
    ) {

        selectedMatchLeft =
            itemId;


        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const area =
            document.getElementById(
                'puzzleInteractiveArea'
            );


        if (area) {

            renderMatchingGrid(
                topic.puzzle,
                area
            );

        }
    }


    /* =========================================================
       MATCH RIGHT
    ========================================================= */

    function selectMatchRight(
        matchId
    ) {

        if (!selectedMatchLeft) {
            return;
        }


        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const puzzle =
            getModeData(
                topic,
                'puzzle'
            );


        const targetItem =
            puzzle.items.find(
                item =>
                    item.id ===
                    selectedMatchLeft
            );


        if (
            targetItem &&
            targetItem.matchId ===
                matchId
        ) {

            matchingPairsState[
                selectedMatchLeft
            ] = matchId;


            selectedMatchLeft = null;


            const area =
                document.getElementById(
                    'puzzleInteractiveArea'
                );


            renderMatchingGrid(
                puzzle,
                area
            );


            /* -----------------------------------------
               Check completion
            ----------------------------------------- */

            if (
                Object.keys(
                    matchingPairsState
                ).length ===
                puzzle.items.length
            ) {

                const modeKey =
                    getModeKey(
                        topic.id,
                        'puzzle'
                    );


                const isFirst =
                    !gameState.completedModes[
                        modeKey
                    ];


                gameState.completedModes[
                    modeKey
                ] = true;


                updateChapterUnlock(
                    activeChapterId
                );


                if (isFirst) {

                    addRewards(
                        puzzle.reward
                    );


                    setChronoMessage(
                        `Incredible work! All historical pairs matched accurately. +${puzzle.reward?.xp || 0} XP!`
                    );

                }


                const feedbackEl =
                    document.getElementById(
                        'puzzleFeedback'
                    );


                if (feedbackEl) {

                    feedbackEl.style.display =
                        'block';


                    feedbackEl.className =
                        'p-3 rounded alert alert-success text-dark mt-3';


                    feedbackEl.innerHTML = `

                        <div
                            style="
                                font-weight:bold;
                                font-size:13px;
                            "
                        >
                            🎉 ALL PAIRS MATCHED!
                        </div>


                        <div
                            style="
                                font-size:12px;
                                margin-top:3px;
                            "
                        >
                            You have mastered
                            these historical connections!
                        </div>

                    `;

                }


                renderAdventureMap();

            }

        } else {

            const feedbackEl =
                document.getElementById(
                    'puzzleFeedback'
                );


            if (feedbackEl) {

                feedbackEl.style.display =
                    'block';


                feedbackEl.className =
                    'p-2 rounded alert alert-danger text-dark mt-2';


                feedbackEl.innerHTML =
                    '❌ That match does not align! Re-read the clues and try again.';


                setTimeout(
                    () => {
                        feedbackEl.style.display =
                            'none';
                    },
                    2200
                );

            }


            selectedMatchLeft = null;


            const area =
                document.getElementById(
                    'puzzleInteractiveArea'
                );


            renderMatchingGrid(
                puzzle,
                area
            );

        }

    }


    /* =========================================================
       GENERIC PUZZLE FALLBACK
    ========================================================= */

    function renderGenericPuzzle(
        puzzle,
        area,
        isDone
    ) {

        if (
            Array.isArray(
                puzzle.options
            )
        ) {

            let html = `
                <div class="d-grid gap-2">
            `;


            puzzle.options.forEach(
                (option, index) => {

                    html += `

                        <button
                            class="
                                btn
                                btn-outline-info
                            "
                            onclick="
                                KaalchakraEngine.checkGenericPuzzle(${index})
                            "
                        >
                            ${String.fromCharCode(65 + index)}.
                            ${option}
                        </button>

                    `;

                }
            );


            html += `
                </div>
                <div
                    id="genericPuzzleFeedback"
                    class="mt-3"
                    style="display:none;"
                ></div>
            `;


            area.innerHTML =
                html;

        } else {

            area.innerHTML = `

                <div
                    class="alert alert-info"
                >
                    This puzzle uses a custom
                    interaction that has not
                    been configured yet.
                </div>

            `;

        }

    }


    /* =========================================================
       GENERIC PUZZLE CHECK
    ========================================================= */

    function checkGenericPuzzle(
        selectedIndex
    ) {

        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const puzzle =
            getModeData(
                topic,
                'puzzle'
            );


        if (!puzzle) {
            return;
        }


        const feedback =
            document.getElementById(
                'genericPuzzleFeedback'
            );


        if (!feedback) {
            return;
        }


        feedback.style.display =
            'block';


        if (
            selectedIndex ===
            puzzle.correct
        ) {

            const modeKey =
                getModeKey(
                    topic.id,
                    'puzzle'
                );


            const first =
                !gameState.completedModes[
                    modeKey
                ];


            gameState.completedModes[
                modeKey
            ] = true;


            updateChapterUnlock(
                activeChapterId
            );


            if (first) {

                addRewards(
                    puzzle.reward
                );

            }


            feedback.className =
                'p-3 alert alert-success text-dark';


            feedback.innerHTML =
                `🎉 Correct! ${puzzle.explanation || ''}`;


            renderAdventureMap();

        } else {

            feedback.className =
                'p-3 alert alert-danger text-dark';


            feedback.innerHTML =
                '❌ Not quite right. Examine the evidence and try again.';

        }

    }


    /* =========================================================
       THEORETICAL MODE
    ========================================================= */

    function renderTheoreticalView(
        chapter,
        container
    ) {

        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const theoretical =
            getTheoreticalData(
                topic
            );


        if (!theoretical) {

            container.innerHTML = `

                <div
                    class="alert alert-warning"
                >
                    Theoretical content is not
                    available for this topic yet.
                </div>

            `;

            return;
        }


        const isDone =
            gameState.completedModes[
                getModeKey(
                    topic.id,
                    'theoretical'
                )
            ];


        let factsHTML = '';


        (
            theoretical.keyFacts ||
            []
        ).forEach(
            fact => {

                factsHTML += `

                    <li
                        class="mb-1"
                        style="
                            font-size:12px;
                            color:#ddd2bf;
                        "
                    >
                        ${fact}
                    </li>

                `;

            }
        );


        let vocabHTML = '';


        if (
            Array.isArray(
                theoretical.vocabulary
            ) &&
            theoretical.vocabulary.length
        ) {

            vocabHTML += `

                <div
                    class="row g-2 mt-1"
                >

            `;


            theoretical.vocabulary.forEach(
                vocab => {

                    vocabHTML += `

                        <div
                            class="col-12 col-md-6"
                        >

                            <div
                                class="p-2"
                                style="
                                    background:
                                        rgba(0,0,0,0.3);
                                    border:
                                        1px solid
                                        rgba(255,213,91,0.2);
                                    border-radius:8px;
                                "
                            >

                                <span
                                    style="
                                        font-weight:bold;
                                        color:#ffd764;
                                        font-size:12px;
                                    "
                                >
                                    ${vocab.term}:
                                </span>


                                <span
                                    style="
                                        font-size:11px;
                                        color:#d0c4ad;
                                    "
                                >
                                    ${vocab.definition}
                                </span>

                            </div>

                        </div>

                    `;

                }
            );


            vocabHTML += `
                </div>
            `;

        }


        /* ---------------------------------------------
           Optional MCQs
        --------------------------------------------- */

        let questionsHTML = '';


        if (
            Array.isArray(
                theoretical.questions
            )
        ) {

            questionsHTML += `

                <div
                    class="mt-4"
                >

                    <div
                        style="
                            font-size:12px;
                            font-weight:bold;
                            color:#ffd764;
                            margin-bottom:8px;
                        "
                    >
                        🧠 KNOWLEDGE CHECK
                    </div>

            `;


            theoretical.questions.forEach(
                (question, qIndex) => {

                    questionsHTML += `

                        <div
                            class="
                                theoretical-question
                                p-3
                                mb-3
                            "
                            style="
                                background:
                                    rgba(255,255,255,0.03);
                                border:
                                    1px solid
                                    rgba(255,255,255,0.1);
                                border-radius:12px;
                            "
                        >

                            <div
                                style="
                                    color:#f4edd9;
                                    font-size:12px;
                                    font-weight:bold;
                                    margin-bottom:8px;
                                "
                            >
                                ${qIndex + 1}.
                                ${question.question || question.text || ''}
                            </div>

                    `;


                    (
                        question.options ||
                        []
                    ).forEach(
                        (option, optionIndex) => {

                            questionsHTML += `

                                <button
                                    type="button"
                                    class="
                                        btn
                                        btn-outline-success
                                        w-100
                                        text-start
                                        mb-2
                                    "
                                    style="
                                        font-size:11px;
                                    "
                                    onclick="
                                        KaalchakraEngine.answerTheoreticalQuestion(
                                            ${qIndex},
                                            ${optionIndex}
                                        )
                                    "
                                >
                                    ${String.fromCharCode(65 + optionIndex)}.
                                    ${option}
                                </button>

                            `;

                        }
                    );


                    questionsHTML += `

                            <div
                                id="theoreticalFeedback-${qIndex}"
                                class="mt-2"
                                style="display:none;"
                            ></div>

                        </div>

                    `;

                }
            );


            questionsHTML += `
                </div>
            `;

        }


        container.innerHTML = `

            <div
                class="
                    d-flex
                    justify-content-between
                    align-items-center
                    mb-3
                "
            >

                <button
                    class="
                        btn
                        btn-sm
                        btn-outline-secondary
                        text-light
                    "
                    onclick="
                        KaalchakraEngine.backToTopics()
                    "
                    style="
                        border-radius:20px;
                        font-size:11px;
                    "
                >
                    ← Back to Topics
                </button>


                <span
                    class="badge bg-success"
                >
                    📖 THEORETICAL MODE
                </span>

            </div>


            <div
                class="
                    info-content
                    p-3
                    mb-3
                "
                style="
                    background:
                        rgba(0,0,0,0.45);
                    border:
                        1px solid
                        rgba(132,168,73,0.4);
                    border-radius:14px;
                    max-height:55vh;
                    overflow-y:auto;
                "
            >

                <h6
                    style="
                        color:#b2de68;
                        font-weight:bold;
                        font-size:16px;
                        margin-bottom:8px;
                    "
                >
                    📖 ${theoretical.title || topic.title}
                </h6>


                <p
                    style="
                        font-size:13px;
                        line-height:1.6;
                        color:#f4edd9;
                        margin-bottom:15px;
                    "
                >
                    ${
                        theoretical.summary ||
                        ''
                    }
                </p>


                ${
                    factsHTML
                        ? `
                            <div
                                style="
                                    font-size:12px;
                                    font-weight:bold;
                                    color:#ffd764;
                                    margin-bottom:6px;
                                "
                            >
                                KEY STUDY POINTS
                            </div>

                            <ul
                                style="
                                    padding-left:20px;
                                    margin-bottom:15px;
                                "
                            >
                                ${factsHTML}
                            </ul>
                        `
                        : ''
                }


                ${
                    theoretical.didYouKnow
                        ? `

                            <div
                                class="p-3 mb-3"
                                style="
                                    background:
                                        rgba(255,215,64,0.1);
                                    border-left:
                                        4px solid #ffd764;
                                    border-radius:8px;
                                "
                            >

                                <div
                                    style="
                                        font-weight:bold;
                                        color:#ffe69a;
                                        font-size:12px;
                                        margin-bottom:2px;
                                    "
                                >
                                    💡 DID YOU KNOW?
                                </div>


                                <div
                                    style="
                                        font-size:12px;
                                        color:#ede3ce;
                                    "
                                >
                                    ${theoretical.didYouKnow}
                                </div>

                            </div>

                        `
                        : ''
                }


                ${
                    vocabHTML
                        ? `

                            <div
                                style="
                                    font-size:12px;
                                    font-weight:bold;
                                    color:#ffd764;
                                    margin-top:10px;
                                    margin-bottom:4px;
                                "
                            >
                                TEXTBOOK VOCABULARY & TERMS
                            </div>

                            ${vocabHTML}

                        `
                        : ''
                }


                ${questionsHTML}

            </div>


            <div
                class="text-center"
            >

                <button
                    class="start-button py-2"
                    onclick="
                        KaalchakraEngine.completeTheoreticalMode()
                    "
                    ${
                        isDone
                            ? 'disabled style="opacity:0.75"'
                            : ''
                    }
                >

                    ${
                        isDone
                            ? '✓ TOPIC KNOWLEDGE MASTERED'
                            : '🎓 I HAVE READ & MASTERED THIS TOPIC (+20 XP)'
                    }

                </button>

            </div>

        `;

    }


    /* =========================================================
       THEORETICAL QUESTION
    ========================================================= */

    function answerTheoreticalQuestion(
        questionIndex,
        optionIndex
    ) {

        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const theoretical =
            getTheoreticalData(
                topic
            );


        if (
            !theoretical ||
            !Array.isArray(
                theoretical.questions
            )
        ) {
            return;
        }


        const question =
            theoretical.questions[
                questionIndex
            ];


        if (!question) {
            return;
        }


        const feedback =
            document.getElementById(
                `theoreticalFeedback-${questionIndex}`
            );


        if (!feedback) {
            return;
        }


        feedback.style.display =
            'block';


        if (
            optionIndex ===
            question.correct
        ) {

            feedback.className =
                'alert alert-success text-dark p-2';


            feedback.innerHTML = `

                <strong>
                    ✓ Correct!
                </strong>

                ${
                    question.explanation
                        ? `<div style="font-size:11px;margin-top:3px;">
                            ${question.explanation}
                           </div>`
                        : ''
                }

            `;

        } else {

            feedback.className =
                'alert alert-danger text-dark p-2';


            feedback.innerHTML = `

                <strong>
                    ✗ Not quite.
                </strong>

                ${
                    question.explanation
                        ? `<div style="font-size:11px;margin-top:3px;">
                            ${question.explanation}
                           </div>`
                        : ''
                }

            `;

        }

    }


    /* =========================================================
       COMPLETE THEORETICAL MODE
    ========================================================= */

    function completeTheoreticalMode() {

        const chapter =
            getChapter(
                activeChapterId
            );


        const topic =
            getTopic(
                chapter,
                activeTopicId
            );


        const theoretical =
            getTheoreticalData(
                topic
            );


        if (!theoretical) {
            return;
        }


        const modeKey =
            getModeKey(
                topic.id,
                'theoretical'
            );


        const isFirst =
            !gameState.completedModes[
                modeKey
            ];


        gameState.completedModes[
            modeKey
        ] = true;


        updateChapterUnlock(
            activeChapterId
        );


        if (isFirst) {

            const reward =
                theoretical.reward ||
                {
                    xp: 20,
                    coins: 5
                };


            addRewards(
                reward
            );


            setChronoMessage(
                `Great learning! You mastered the key facts for "${topic.title}". +${reward.xp || 0} XP and +${reward.coins || 0} coins!`
            );

        }


        renderAdventureMap();


        renderChapterModal();
    }


    /* =========================================================
       OLD INFO MODE COMPATIBILITY
    ========================================================= */

    function completeInfoMode() {

        completeTheoreticalMode();

    }


    /* =========================================================
       COLLECT RELIC
    ========================================================= */

    function collectRelic(
        relicId
    ) {

        if (
            gameState.collectedRelics
                .includes(relicId)
        ) {
            return;
        }


        gameState.collectedRelics.push(
            relicId
        );


        gameState.xp += 10;

        gameState.coins += 5;


        saveState();


        const element =
            document.getElementById(
                relicId
            );


        if (element) {

            element.style.display =
                'none';

        }


        triggerScreenFlash();


        setChronoMessage(
            'Amazing! You discovered an ancient historical relic on the path. +10 XP and +5 coins!'
        );
    }


    /* =========================================================
       CHRONO MESSAGE
    ========================================================= */

    function setChronoMessage(
        text
    ) {

        const element =
            document.getElementById(
                'chronoMessage'
            );


        if (element) {

            element.innerText =
                text;

        }

    }


    /* =========================================================
       SELECT TOPIC
    ========================================================= */

    function selectTopic(
        topicId
    ) {

        activeTopicId =
            topicId;


        activeMode =
            null;


        puzzleUserSelection =
            null;


        selectedMatchLeft =
            null;


        matchingPairsState =
            {};


        renderChapterModal();
    }


    /* =========================================================
       LAUNCH MODE
    ========================================================= */

    function launchMode(
        modeName
    ) {

        if (
            modeName === 'info'
        ) {

            modeName =
                'theoretical';

        }


        activeMode =
            modeName;


        puzzleUserSelection =
            null;


        selectedMatchLeft =
            null;


        matchingPairsState =
            {};


        renderChapterModal();
    }


    /* =========================================================
       BACK TO TOPICS
    ========================================================= */

    function backToTopics() {

        activeMode =
            null;


        puzzleUserSelection =
            null;


        selectedMatchLeft =
            null;


        matchingPairsState =
            {};


        renderChapterModal();
    }


    /* =========================================================
       REFRESH SERVER PROGRESS
       Used by the DB-driven stage controller after a mode is completed.
    ========================================================= */

    async function refreshProgress() {
        if (window.KaalchakraProgress && typeof window.KaalchakraProgress.load === 'function') {
            await window.KaalchakraProgress.load();
            const p = window.KaalchakraProgress.state;
            if (p) {
                gameState.xp = Number(p.xp) || 0;
                gameState.coins = Number(p.coins) || 0;
                gameState.score = Number(p.score) || 0;
                gameState.completedModes = { ...(p.completedModes || {}) };
                updateHUD();
            }
            return getState();
        }
        await loadState();
        return getState();
    }


    /* =========================================================
       GET CURRENT STATE
    ========================================================= */

    function getState() {

        return {
            ...gameState,

            completedModes: {
                ...gameState.completedModes
            },

            collectedRelics: [
                ...gameState.collectedRelics
            ]
        };

    }


    /* =========================================================
       REFRESH CHAPTER DATA
    ========================================================= */

    function refreshChapters() {

        renderAdventureMap();

    }


    /* =========================================================
       INITIALIZATION
    ========================================================= */

    async function init() {

    try {

        /*
         * FIRST:
         * Load chapters/stages/games from MySQL.
         */

        await loadChapterContent();


        /*
         * SECOND:
         * Load player progress.
         */

        await loadState();


        /*
         * THIRD:
         * Render the journey using
         * the database chapters.
         */

        renderAdventureMap();

        window.dispatchEvent(new CustomEvent('kaalchakra:content-ready', {
            detail: {
                chapters: getChapters()
            }
        }));


        /*
         * Recalculate layout after browser
         * finishes rendering.
         */

        requestAnimationFrame(() => {

            adjustJourneyRoadHeight();

            positionPlayerToken();

        });


    } catch (error) {

        console.error(
            'KaalChakra initialization failed:',
            error
        );

    }


}


    /* =========================================================
       DOM READY
    ========================================================= */

    if (
        document.readyState ===
        'loading'
    ) {

        document.addEventListener(
            'DOMContentLoaded',
            init
        );

    } else {

        init();

    }


    /* =========================================================
       PUBLIC API
    ========================================================= */

    window.KaalchakraEngine = {

        /* Chapter */

        openChapter:
            openChapter,

        getChapters:
            getChapters,

        refreshChapters:
            refreshChapters,


        /* Topic */

        selectTopic:
            selectTopic,


        /* Modes */

        launchMode:
            launchMode,

        backToTopics:
            backToTopics,


        /* Mystery */

        checkMysteryAnswer:
            checkMysteryAnswer,


        /* Puzzle */

        moveSequence:
            moveSequence,

        checkSequenceSolution:
            checkSequenceSolution,

        selectMatchLeft:
            selectMatchLeft,

        selectMatchRight:
            selectMatchRight,

        checkGenericPuzzle:
            checkGenericPuzzle,


        /* Theoretical */

        answerTheoreticalQuestion:
            answerTheoreticalQuestion,

        completeTheoreticalMode:
            completeTheoreticalMode,

        /* Backward compatibility */

        completeInfoMode:
            completeInfoMode,


        /* Relics */

        collectRelic:
            collectRelic,


        /* State */

        getState:
            getState,

        refreshProgress:
            refreshProgress,

        getChapterProgress:
            getChapterProgress

    };

function showContentError(message) {

    const mapContainer =
        document.querySelector(
            '.adventure-map'
        );


    if (!mapContainer) {
        return;
    }


    mapContainer.innerHTML = `

        <div
            class="text-center p-5"
            style="
                color:#ffd45e;
                max-width:600px;
                margin:80px auto;
            "
        >

            <div
                style="
                    font-size:55px;
                    margin-bottom:15px;
                "
            >
                ⚠️
            </div>


            <h4>
                HISTORICAL JOURNEY UNAVAILABLE
            </h4>


            <p
                style="
                    color:#c4b9a0;
                    font-size:14px;
                "
            >
                ${message}
            </p>


            <button
                class="btn btn-warning"
                onclick="location.reload()"
            >
                ↻ TRY AGAIN
            </button>

        </div>

    `;

}

    /* =========================================================
       BACKWARD COMPATIBILITY
    ========================================================= */

    window.openChapter =
        openChapter;


})();
