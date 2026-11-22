CHESS THINKING METHOD - UPDATED PGN GAME REVIEW
===============================================
This build is based on your newer ChessApp(1).zip, not the earlier app.

WHAT WAS PRESERVED
- Play vs Stockfish with adjustable strength
- PGN import, FEN import, uploaded-game selection
- Review/rewind move navigation
- Interactive board and analysis variations
- Evaluation graph, position arrows and last-move highlights
- Play from any reviewed position

WHAT WAS ADDED
- Full twelve-question weakness scan in the exact order of Book 1 Foundation
- Immediate written narration for each selected PGN move
- Optional Listen / Stop browser voice playback for that narration
- Full-game Stockfish scoring on demand (Quick, Standard, Thorough)
- Jump-to-move alerts for blunders, mistakes, inaccuracies and mate changes
- Book-pattern summary around missed opportunities
- Downloadable full-game narrated review (.txt)

HOW TO USE
1. Run START_APP_WINDOWS.bat as before.
2. Open 'Import game / position' in the sidebar, upload or paste a PGN,
   select your colour, then click Load PGN game.
3. Navigate through the move list. Written narration appears immediately.
   Use 'Listen' to hear it read aloud (requires browser speech support).
4. Click 'Analyse uploaded game - all 12 weaknesses' to score the moves.
   Select a missed-opportunity alert to jump to it.
5. Expand '12 weakness questions' to see all checks and concrete findings.
6. Optionally export the full narration as text.

IMPORTANT
- Exactly one Stockfish engine is used. The twelve book categories are
  checked separately by chess position rules, not by twelve engines.
- A detected positional pattern is not proof of a profitable tactic.
- Engine results are estimates and depend on analysis strength/time.
- This version's book review applies to uploaded PGN games. Existing
  interactive play and FEN workflows have been retained.

BLUNDER EXPLANATIONS - REVISED
- Each scored mistake now separates the actual played move and the opponent's
  strongest reply from Stockfish's best-move alternative. Previously these
  variations could be conflated in the narration.
- When there is a verified immediate capture, checkmate, check, or attack,
  the narration says exactly what was captured/threatened on which square.
- A deeper extra engine pass is performed on significant errors to improve
  the accuracy and clarity of the refutation line.
- If the continuation doesn't show a concrete tactical cause, the app says
  so rather than inventing a reason based on unrelated weakness flags.
- All 12 book questions remain available independently in their original order.
- The Listen and download features use the revised move-specific explanation.

INTERMEDIATE-LEVEL COACH NARRATION
- Natural-language commentary now explains the move, the verified opponent
  continuation, and the better alternative without listing long engine moves.
- Routine recaptures are recognized and are not called free pawns or tactics.
  E.g., ...Nxd5 after cxd5 is a recapture; ...Nxf4 followed by exf4 is a trade.
- The coach only says what the position/engine line supports. If an evaluation
  worsens but no clear tactic appears, it explicitly avoids inventing a cause.
- Raw engine variations and numerical evaluation are inside a collapsed
  "Engine lines and numerical score" panel rather than spoken aloud.
- The 'Question for next game' is tied to a grounded weakness category when
  one can be established. The complete 12-question checklist is preserved.
- Listening and full-game narration export use the same simpler commentary.

STOCKFISH COACH REPLAY (THIS BUILD)
- Upload a PGN and choose "Analyse uploaded game - all 12 weaknesses".
- For any reviewed move, "Your move + reply" replays the move actually
  played and Stockfish's principal variation from the resulting position.
- "Better move + reply" replays Stockfish's stronger candidate and its line
  from the position *before* the mistake.
- Back / Next updates the MAIN chessboard and highlights each actual move.
  Each replay step includes a concise explanation and its own Listen button.
- Exit replay restores the selected PGN move; the original PGN is never
  overwritten. "Play from this position" branches into a separate game.
- "Re-analyse this move deeply" re-scores just the selected move and both
  continuations (higher effort), leaving other moves' analysis intact.
- Coach explanations prioritize verifiable checks, captures, recaptures,
  piece attacks, and knight centralisation, rather than unrelated flags.
- A short engine line may not prove why an evaluation dropped. The coach
  explicitly says so when necessary. Engine lines are sample continuations,
  not a proof that the opponent must follow exactly those moves.
- The existing PGN review, raw engine lines, 12 book weakness questions,
  Listen/Stop narration, evaluation graph and Stockfish play were retained.

TESTING NOTE
- Python syntax compilation and ZIP checks were carried out in Linux.
- The Windows engine and Streamlit interactive session require an actual
  Windows run; these could not be exercised in this environment.
