# AILT9019 Gallery

Reproducible local snapshot of the course website, virtual exhibition, peer review, voting, and Staff workspace. The seed includes 50 fictional projects with fixed codes A01–E50, public sample videos, and three assigned reviews per demo student.

## Run from a clean clone

Requires Python 3.11+.

```sh
git clone https://github.com/JiaWei22/ailt9019-gallery.git
cd ailt9019-gallery
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-rehearsal.txt
python run_demo.py
```

Open the [course homepage](http://127.0.0.1:8084/review-system/w13/course/). Use port 8086 instead with `python run_demo.py --port 8086` if 8084 is already in use.

| Role | Sign-in page | Demo account | Demo password |
| --- | --- | --- | --- |
| Student | [/review-system/w13/login/](http://127.0.0.1:8084/review-system/w13/login/) | 123456 | 123456 |
| Staff | [/review-system/w13/manage/](http://127.0.0.1:8084/review-system/w13/manage/) | 654321 | 654321 |

Each run creates a separate SQLite database in `local_data/` and applies all migrations. `python run_demo.py --seed-only` prepares a database without starting the server. The sample data is generated from `demo/projects.json`. YouTube playback and thumbnails require internet access and depend on YouTube availability.

To check the student and Staff workflows on independent fixtures:

```sh
mkdir -p local_data
python verify_simplified_journey.py
python verify_account_switching.py
```

The demo binds to loopback and ignores activity date windows for testing. Use separate production settings, credentials, and course data for deployment. The repository contains source and synthetic fixtures. Local databases, active sessions, and course submissions are outside the snapshot.
