/**
 * KAALCHAKRA - Background Animation & Atmosphere FX Controller
 *
 * Updated for the Flask version of KaalChakra.
 *
 * Manages:
 * - Scroll-reactive celestial and era atmosphere transitions
 * - Continuous ambient fireflies/time-particles in the active viewport
 * - Parallax movement of moon and stars as the player journeys through time
 * - Golden nocturnal visual theme
 *
 * Notes:
 * - This file is frontend-only; no PHP endpoints are used.
 * - The controller is safe to initialize more than once.
 * - Scroll/resize work is throttled with requestAnimationFrame for smoother
 *   performance on long chapter maps.
 */

(function () {
    'use strict';

    // KaalChakra contains 10 chapters.
    // Each pair of chapters shares an era.
    const ERA_GRADIENTS = [
        {
            // Era 1 (Ch 1-2): Dawn of History & Prehistoric
            start: '#101a35',
            mid1: '#17284b',
            mid2: '#34556c',
            mid3: '#597456',
            end: '#304b32'
        },
        {
            // Era 2 (Ch 3-4): Indus Bronze Age & Vedic Dawn
            start: '#0e182b',
            mid1: '#16253d',
            mid2: '#284457',
            mid3: '#4a5b48',
            end: '#2c3b28'
        },
        {
            // Era 3 (Ch 5-6): Mahajanapadas & Spiritual Awakening
            start: '#151329',
            mid1: '#231b38',
            mid2: '#3d304f',
            mid3: '#5b4c48',
            end: '#332622'
        },
        {
            // Era 4 (Ch 7-8): Mauryan Empire & Coastal Trade
            start: '#1a1221',
            mid1: '#2b172a',
            mid2: '#472738',
            mid3: '#5a4338',
            end: '#2f221c'
        },
        {
            // Era 5 (Ch 9-10): Classical Golden Age & Ancient Sciences
            start: '#0f1628',
            mid1: '#1b243d',
            mid2: '#323a54',
            mid3: '#544941',
            end: '#2d261e'
        }
    ];

    let gameWorld = null;
    let moonElement = null;
    let starsContainer = null;

    let activeFireflies = [];

    let particleTimer = null;
    let cleanupTimer = null;

    let scrollFrame = null;
    let resizeFrame = null;

    let initialized = false;

    const MAX_VIEWPORT_FIREFLIES = 14;
    const PARTICLE_INTERVAL = 1200;
    const FIREFLY_LIFETIME = 9000;

    /**
     * Initialize background effects.
     */
    function initBackgroundFX() {

        const nextGameWorld = document.getElementById('gameWorld');

        if (!nextGameWorld) {
            return false;
        }

        /*
         * Prevent duplicate listeners and particle loops
         * if init() is called more than once.
         */
        if (initialized && gameWorld === nextGameWorld) {
            onScrollAtmosphere();
            return true;
        }

        cleanup();

        gameWorld = nextGameWorld;

        moonElement = document.querySelector('.moon');
        starsContainer = document.querySelector('.stars');

        // Create the star field.
        createStarField();

        // Scroll listener.
        window.addEventListener(
            'scroll',
            requestAtmosphereUpdate,
            {
                passive: true
            }
        );

        // Resize listener.
        window.addEventListener(
            'resize',
            requestResizeUpdate,
            {
                passive: true
            }
        );

        initialized = true;

        // Initial atmosphere update.
        onScrollAtmosphere();

        // Start fireflies.
        startViewportParticleLoop();

        return true;
    }

    /**
     * Clean up listeners, timers and particles.
     *
     * Useful when the dashboard/game world is rebuilt dynamically.
     */
    function cleanup() {

        window.removeEventListener(
            'scroll',
            requestAtmosphereUpdate
        );

        window.removeEventListener(
            'resize',
            requestResizeUpdate
        );

        if (particleTimer) {
            clearInterval(particleTimer);
            particleTimer = null;
        }

        if (cleanupTimer) {
            clearInterval(cleanupTimer);
            cleanupTimer = null;
        }

        if (scrollFrame) {
            cancelAnimationFrame(scrollFrame);
            scrollFrame = null;
        }

        if (resizeFrame) {
            cancelAnimationFrame(resizeFrame);
            resizeFrame = null;
        }

        activeFireflies.forEach(function (firefly) {

            if (
                firefly &&
                firefly.parentNode
            ) {
                firefly.parentNode.removeChild(firefly);
            }

        });

        activeFireflies = [];

        initialized = false;
    }

    /**
     * Create a lightweight field of twinkling stars.
     */
    function createStarField() {

        if (!starsContainer) {
            return;
        }

        starsContainer.innerHTML = '';

        const starCount = 35;

        for (let i = 0; i < starCount; i++) {

            const star = document.createElement('span');

            star.className = 'star';

            star.style.top =
                (Math.random() * 95) + '%';

            star.style.left =
                (Math.random() * 98) + '%';

            star.style.animationDelay =
                (Math.random() * 3) + 's';

            star.style.animationDuration =
                (1.5 + Math.random() * 2) + 's';

            // Randomly create larger stars.
            if (Math.random() > 0.6) {

                star.style.width = '4px';
                star.style.height = '4px';

                star.style.boxShadow =
                    '0 0 6px #fff8c7';
            }

            starsContainer.appendChild(star);
        }
    }

    /**
     * Request one atmosphere update on the next
     * animation frame.
     *
     * This prevents the scroll handler from doing
     * expensive work hundreds of times per second.
     */
    function requestAtmosphereUpdate() {

        if (scrollFrame) {
            return;
        }

        scrollFrame = requestAnimationFrame(function () {

            scrollFrame = null;

            onScrollAtmosphere();
        });
    }

    /**
     * Request one resize update on the next frame.
     */
    function requestResizeUpdate() {

        if (resizeFrame) {
            return;
        }

        resizeFrame = requestAnimationFrame(function () {

            resizeFrame = null;

            onScrollAtmosphere();
        });
    }

    /**
     * Update:
     * - background gradient
     * - moon position
     * - star parallax
     *
     * based on the player's scroll position.
     */
    function onScrollAtmosphere() {

        if (!gameWorld) {
            return;
        }

        const scrollY =
            window.scrollY ||
            window.pageYOffset ||
            0;

        const viewportHeight =
            window.innerHeight || 1;

        const maxScroll = Math.max(
            document.documentElement.scrollHeight -
            viewportHeight,
            1
        );

        const scrollFraction = Math.min(
            Math.max(
                scrollY / maxScroll,
                0
            ),
            1
        );

        /*
         * Determine the current era.
         */
        const eraIndexFloat =
            scrollFraction *
            (ERA_GRADIENTS.length - 1);

        const currentEraIndex = Math.min(
            Math.floor(eraIndexFloat),
            ERA_GRADIENTS.length - 1
        );

        const nextEraIndex = Math.min(
            currentEraIndex + 1,
            ERA_GRADIENTS.length - 1
        );

        const eraProgress =
            eraIndexFloat -
            currentEraIndex;

        const currentEra =
            ERA_GRADIENTS[currentEraIndex];

        const nextEra =
            ERA_GRADIENTS[nextEraIndex];

        /*
         * Smoothly interpolate every gradient stop.
         */
        const cStart = interpolateHex(
            currentEra.start,
            nextEra.start,
            eraProgress
        );

        const cMid1 = interpolateHex(
            currentEra.mid1,
            nextEra.mid1,
            eraProgress
        );

        const cMid2 = interpolateHex(
            currentEra.mid2,
            nextEra.mid2,
            eraProgress
        );

        const cMid3 = interpolateHex(
            currentEra.mid3,
            nextEra.mid3,
            eraProgress
        );

        const cEnd = interpolateHex(
            currentEra.end,
            nextEra.end,
            eraProgress
        );

        gameWorld.style.background =
            `linear-gradient(to bottom, ` +
            `${cStart} 0%, ` +
            `${cMid1} 28%, ` +
            `${cMid2} 55%, ` +
            `${cMid3} 78%, ` +
            `${cEnd} 100%)`;

        /*
         * Moon parallax.
         */
        if (moonElement) {

            const moonOffsetY =
                scrollY * 0.12;

            const moonOffsetX =
                Math.sin(
                    scrollFraction * Math.PI
                ) * 20;

            moonElement.style.transform =
                `translate3d(` +
                `${moonOffsetX}px, ` +
                `${moonOffsetY}px, 0)`;
        }

        /*
         * Star parallax.
         */
        if (starsContainer) {

            starsContainer.style.transform =
                `translate3d(` +
                `0, ${scrollY * 0.05}px, 0)`;
        }
    }

    /**
     * Interpolate between two hexadecimal colours.
     */
    function interpolateHex(
        hex1,
        hex2,
        factor
    ) {

        const c1 = parseHex(hex1);
        const c2 = parseHex(hex2);

        const r = Math.round(
            c1.r +
            factor *
            (c2.r - c1.r)
        );

        const g = Math.round(
            c1.g +
            factor *
            (c2.g - c1.g)
        );

        const b = Math.round(
            c1.b +
            factor *
            (c2.b - c1.b)
        );

        return (
            `#${toHex(r)}` +
            `${toHex(g)}` +
            `${toHex(b)}`
        );
    }

    /**
     * Convert HEX to RGB.
     */
    function parseHex(hex) {

        let clean =
            String(hex)
                .replace('#', '');

        /*
         * Support shorthand:
         * #fff -> #ffffff
         */
        if (clean.length === 3) {

            clean = clean
                .split('')
                .map(function (c) {
                    return c + c;
                })
                .join('');
        }

        const num =
            parseInt(clean, 16);

        /*
         * Protection against invalid colors.
         */
        if (Number.isNaN(num)) {

            return {
                r: 0,
                g: 0,
                b: 0
            };
        }

        return {
            r: (num >> 16) & 255,
            g: (num >> 8) & 255,
            b: num & 255
        };
    }

    /**
     * Convert number to two-character HEX.
     */
    function toHex(n) {

        const value =
            Math.max(
                0,
                Math.min(
                    255,
                    Number(n) || 0
                )
            );

        const h =
            value.toString(16);

        return h.length === 1
            ? '0' + h
            : h;
    }

    /**
     * Start ambient firefly generation.
     */
    function startViewportParticleLoop() {

        if (particleTimer) {
            clearInterval(particleTimer);
        }

        particleTimer =
            setInterval(function () {

                /*
                 * Don't generate particles while the
                 * browser tab is hidden.
                 */
                if (
                    !gameWorld ||
                    document.hidden
                ) {
                    return;
                }

                removeExpiredFireflies();

                if (
                    activeFireflies.length <
                    MAX_VIEWPORT_FIREFLIES
                ) {
                    spawnViewportFirefly();
                }

            }, PARTICLE_INTERVAL);

        /*
         * Periodic cleanup in case an animation is
         * interrupted.
         */
        cleanupTimer =
            setInterval(function () {

                removeExpiredFireflies();

            }, 2500);
    }

    /**
     * Remove disconnected fireflies from memory.
     */
    function removeExpiredFireflies() {

        activeFireflies =
            activeFireflies.filter(
                function (firefly) {

                    return (
                        firefly &&
                        firefly.isConnected
                    );
                }
            );
    }

    /**
     * Create one firefly around the visible viewport.
     */
    function spawnViewportFirefly() {

        if (!gameWorld) {
            return;
        }

        const scrollY =
            window.scrollY ||
            window.pageYOffset ||
            0;

        const viewHeight =
            window.innerHeight || 1;

        const firefly =
            document.createElement('span');

        firefly.className =
            'firefly dynamic-firefly';

        /*
         * Position inside the currently visible
         * portion of the historical world.
         */
        const topPos =
            scrollY +
            (
                0.2 +
                Math.random() * 0.75
            ) *
            viewHeight;

        const leftPos =
            5 +
            Math.random() * 90;

        firefly.style.top =
            topPos + 'px';

        firefly.style.left =
            leftPos + '%';

        firefly.style.animationDelay =
            (Math.random() * 1.5) + 's';

        firefly.style.animationDuration =
            (5 + Math.random() * 4) + 's';

        /*
         * Fireflies should never interfere with
         * mouse/touch interaction.
         */
        firefly.setAttribute(
            'aria-hidden',
            'true'
        );

        gameWorld.appendChild(firefly);

        activeFireflies.push(firefly);

        /*
         * Remove after the animation lifetime.
         */
        window.setTimeout(function () {

            if (
                firefly &&
                firefly.parentNode
            ) {
                firefly.parentNode.removeChild(
                    firefly
                );
            }

        }, FIREFLY_LIFETIME);
    }

    /**
     * Automatically initialize after DOM loading.
     */
    if (
        document.readyState === 'loading'
    ) {

        document.addEventListener(
            'DOMContentLoaded',
            initBackgroundFX,
            {
                once: true
            }
        );

    } else {

        initBackgroundFX();
    }

    /**
     * Public controller.
     *
     * The game engine can use:
     *
     * KaalchakraBackgroundFX.init()
     * KaalchakraBackgroundFX.update()
     * KaalchakraBackgroundFX.cleanup()
     */
    window.KaalchakraBackgroundFX = {

        init: initBackgroundFX,

        update: onScrollAtmosphere,

        cleanup: cleanup
    };

})();