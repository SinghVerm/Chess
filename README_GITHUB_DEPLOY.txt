CHESS APP — GITHUB / STREAMLIT CLOUD DEPLOYMENT

This package contains the complete cloud-ready app, 100 book puzzles,
and Linux Stockfish installation instructions (packages.txt).
It deliberately excludes the 103 MB Windows-only Stockfish .exe and source tree.

WHAT MUST BE IN YOUR GITHUB REPOSITORY ROOT:
  app.py
  book_puzzle_mode.py
  book_review.py
  coach_layer.py
  requirements.txt
  packages.txt
  book_puzzles/puzzles.json
  book_puzzles/001.png ... 100.png

UPLOAD (RECOMMENDED: GITHUB DESKTOP):
  1. Install and open GitHub Desktop, clone your repo.
  2. Unzip this archive; copy EVERYTHING INSIDE into the cloned repo's root.
  3. GitHub Desktop: Commit to main, then Push origin.
  4. On GitHub, confirm book_puzzles contains puzzles.json and the images.
  5. In Streamlit Community Cloud, redeploy/reboot the app.

WEB UPLOAD ALTERNATIVE:
  Repo -> Add file -> Upload files. Drag files/folders from the extracted
  archive (not the ZIP). Upload in batches if GitHub complains about quantity.
  Confirm the folder structure before committing.

STOCKFISH:
  packages.txt tells Streamlit Cloud to install the Linux Stockfish engine.
  app.py now detects /usr/games/stockfish as well as Windows binaries.
  If the Cloud instance does not install the apt package, check build logs.

NOTE: Book puzzle scans/solutions are material from the book you supplied.
Only upload them to a public repository with the rights owner's permission.
For cloud deployments, progress files stored locally may be reset on restart
or redeployment and are not suitable for persistent per-user accounts.
