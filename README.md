# 🏛️ KaalChakra – The Civilization Builder

> An interactive educational game designed to make learning Indian history more engaging through storytelling, quizzes, puzzles, mystery challenges, and game-based learning.

---

## 📖 About the Project

**KaalChakra – The Civilization Builder** is a software-based educational game that transforms traditional history learning into an interactive gaming experience.

The game is designed around Indian history and civilization, allowing students to explore historical topics through different chapters, stages, quizzes, puzzles, mystery challenges, and informational content.

Instead of learning only through textbooks, players learn by **exploring, answering questions, solving challenges, and progressing through the game**.

The current version of KaalChakra is a **software-only implementation** developed as part of the KaalChakra Workshop.

---

# 📁 Project Structure

The project is organized into frontend and backend components.

```text
Kaalchakra-Workshop/
│
├── Backend/
│   ├── app.py
│   ├── train_autoencoder.py
│   ├── requirements.txt
│   └── ...
│
├── Frontend/
│   ├── assets/
│   │   └── IntroVideos/
│   └── ...
│
└── README.md
```

> The exact structure may change as development continues.

---

# ⚙️ Installation

## 1. Clone the Repository

```bash
git clone https://github.com/Gaurav-Amrutkar27/Kaalchakra-Workshop.git
```

Navigate into the project:

```bash
cd Kaalchakra-Workshop
```

---

## 2. Create a Virtual Environment

Create a virtual environment:

```bash
python -m venv venv
```

### Windows

Activate the environment:

```powershell
venv\Scripts\activate
```

After activation, the terminal should display:

```text
(venv)
```

---

## 3. Install Dependencies

Install the required packages:

```powershell
python -m pip install -r requirements.txt
```

```powershell
python -m pip install -r requirements-dl.txt
```

Navigate to the backend:

```bash
cd Backend
```

```powershell
python -m pip install -r requirements_ir_update.txt
```

Using `python -m pip` ensures that the dependencies are installed into the active project environment.

---

## 4. Train Model

Train with Autoencoder:

```powershell
python train_autoencoder.py
```

Train with LSTM:

```powershell
python train_lstm.py
```

# 🗄️ Database Setup

KaalChakra uses **MySQL** as its database.

Make sure MySQL is installed and running.

Create the required database according to the project's database configuration.

Example:

```sql
CREATE DATABASE kaalchakra_db;
```

Update the database configuration in the backend with your local MySQL credentials.

Example:

```python
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "your_password"
DB_NAME = "kaalchakra_db"
```

> Never commit passwords, API keys, or other sensitive credentials to GitHub.

---

# ▶️ Running the Application

After activating the virtual environment and installing dependencies, start the Flask backend:

```powershell
python app.py
```

The application will normally be available at:

```text
http://127.0.0.1:5000/
```

Open the application in your browser.

---

# 🤖 Training the Autoencoder

If the ML component needs to be trained, run:

```powershell
python train_autoencoder.py
```

Make sure all required ML dependencies are installed in the active virtual environment.

---

# 🔄 Application Workflow

The overall system works as follows:

```text
User
 │
 ▼
Login
 │
 ▼
AI Guide
 │
 ▼
Introduction
 │
 ▼
Knowledge Check
 │
 ▼
Chapter
 │
 ▼
Stage
 │
 ▼
Game Mode
 │
 ├── Puzzle
 │
 ├── Mystery
 │
 ├── Combined
 │
 └── Information
 │
 ▼
Challenge
 │
 ▼
Result
 │
 ▼
Civilization Points
 │
 ▼
Next Stage
```


# 📌 Project Summary

| Component           | Technology                             |
| ------------------- | -------------------------------------- |
| Project             | KaalChakra – The Civilization Builder  |
| Type                | Software Educational Game              |
| Frontend            | HTML, CSS, JavaScript                  |
| Backend             | Python + Flask                         |
| Database            | MySQL                                  |
| Database Connector  | PyMySQL                                |
| AI/ML               | Autoencoder, LSTM                      |
| Game Modes          | Puzzle, Mystery, Combined, Information |
| Educational Content | Indian History                         |
| Target Users        | Students / Learners                    |

---


# 📄 License

This project is developed for educational and innovation purposes.

---

## 🏛️ KaalChakra

**Learn the past. Explore civilization. Build knowledge.**
