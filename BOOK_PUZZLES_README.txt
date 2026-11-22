BOOK 1 FOUNDATION — INTERACTIVE PUZZLE TRAINER

The 100 diagrams and their explanations were extracted from the PDF supplied
in this conversation, The Thinking Method — Foundations, by Akeem Brown.

To use:
  1. Run START_APP_WINDOWS.bat normally.
  2. Choose Mode > Book puzzles in the sidebar.
  3. Solve Puzzle 1, then press Next puzzle. Use the dropdown to jump anywhere.
  4. Click/drag a piece on the board; incorrect moves stay on the board and
     show Try again. Verified book moves are accepted; Stockfish also considers
     near-equal alternatives if the engine is available.
  5. Reveal hints as necessary. The source explanation appears after success.
  6. Your solved list and attempts are kept at book_puzzles/progress.json,
     in the program folder, and persist between sessions.

Important:
  * Four first-move notation inconsistencies were found in the book: puzzles
    6 (Bh7+), 22 (Nxb4), 42 (Qe7+) and 50 (Nxf6+). These are explicitly
    annotated and corrected as playable moves in the app.
  * Full variations are taken only when legal in the extracted diagram.
    Some source responses are incomplete or informal. These puzzles may end
    after the first verified move, rather than inventing a continuation.
  * The app's Stockfish executable is Windows-only; its normal Windows path
    detection is retained. This update could not execute Stockfish here.
  * The conversion checks every puzzle's king count, square geometry, and
    expected first move's basic movement geometry. A handful of printed
    continuations may still need human review because diagrams are screenshots.
  * Book material is included for your own personal study; respect the
    author's distribution rights.
