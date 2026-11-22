"""Interactive, source-grounded practice for the 100 puzzles in Book 1 Foundation.

The user's uploaded PDF supplied the positions, numbered puzzles and printed
solutions. Stockfish checks plausible alternate moves and supplies analysis.
"""
import json
import re
import os
from pathlib import Path
from datetime import datetime, timezone

import chess
import chess.engine
import streamlit as st

BASE = Path(__file__).resolve().parent / "book_puzzles"
PUZZLES = json.loads((BASE / "puzzles.json").read_text(encoding="utf-8"))
BY_ID = {p["number"]: p for p in PUZZLES}
PROGRESS_FILE = BASE / "progress.json"

# Extract SAN only from numbered lines of the book's printed solution.
SAN_RE = re.compile(r"O-O-O[+#]?|O-O[+#]?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?")
NUM_RE = re.compile(r"(?<![A-Za-z])\d+\s*\.\s*")


def normalized_solution(puzzle):
    text = puzzle["solution"]
    replacements = {
        6: ("Bxh7+", "Bh7+"),
        22: ("Nb4", "Nxb4"),
        42: ("Qe2+ to Qe7+", "Qe7+"),
        50: ("Nf6+", "Nxf6+"),
    }
    if puzzle["number"] in replacements:
        a, b = replacements[puzzle["number"]]
        text = text.replace(a, b, 1)
    return text


def parse_book_line(puzzle):
    """Keep only verified legal SAN moves, including printed opponent replies."""
    board = chess.Board(puzzle["fen"])
    try:
        first = board.parse_san(puzzle["first_move"].replace("++", "+"))
    except ValueError:
        return [], "The printed first move could not be verified on this diagram."
    plan = [first]
    board.push(first)
    # We expect the first candidate to be the same as the corrected first move.
    lines = normalized_solution(puzzle).splitlines()
    tokens = []
    for line in lines:
        if not NUM_RE.search(line):
            continue
        # A single printed line may contain multiple moves, e.g. 1.Bxh7+ Kxh7 2.Qxd5.
        move_text = NUM_RE.sub(" ", line)
        tokens.extend(SAN_RE.findall(move_text))
    if tokens:
        tokens = tokens[1:]
    for token in tokens:
        try:
            move = board.parse_san(token.replace("++", "+"))
        except (ValueError, AssertionError):
            # Don't fabricate any moves from an ambiguous or broken printed line.
            break
        plan.append(move)
        board.push(move)
    return plan, ""


def read_progress():
    if not PROGRESS_FILE.exists():
        return {}
    try:
        value = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}


def save_progress(progress):
    """Persist progress across app restarts when the local folder is writable."""
    try:
        tmp = PROGRESS_FILE.with_name(PROGRESS_FILE.name + ".tmp")
        tmp.write_text(json.dumps(progress, indent=2), encoding="utf-8")
        os.replace(tmp, PROGRESS_FILE)
    except OSError:
        # Session progress still works if the app is run from a read-only folder.
        pass


def start(number):
    p = BY_ID[number]
    plan, error = parse_book_line(p)
    s = st.session_state
    s.book_puzzle_number = number
    s.book_puzzle_board_fen = p["fen"]
    s.book_puzzle_history = []
    s.book_puzzle_plan = [m.uci() for m in plan]
    s.book_puzzle_cursor = 0
    s.book_puzzle_wrong = 0
    s.book_puzzle_status = "playing"
    s.book_puzzle_notice = ""
    s.book_puzzle_hint = 0
    s.book_puzzle_solution = False
    s.book_puzzle_parse_error = error
    s.book_puzzle_last_nonce = None
    s.book_puzzle_last_info = ""
    s.book_puzzle_branch = "guided"  # Wrong moves branch into a game against Stockfish.
    s.book_puzzle_engine_pending = False


def _score_side(info, board):
    return info["score"].pov(board.turn).score(mate_score=100000)


def engine_alternative(board, move, engine_path):
    """Approve a near-equal alternative, but never falsely claim it is in the book."""
    if not engine_path or move not in board.legal_moves:
        return False, ""
    try:
        with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
            infos = engine.analyse(board, chess.engine.Limit(time=.35), multipv=min(4, board.legal_moves.count()))
            if isinstance(infos, dict):
                infos = [infos]
            values = [(_score_side(x, board), x["pv"][0]) for x in infos if x.get("pv") and x.get("score")]
            if not values:
                return False, ""
            best_score = max(v for v, _ in values)
            for score, candidate in values:
                if candidate == move and best_score - score <= 35:
                    return True, "Stockfish also considers this a strong alternative, although the book shows another move."
    except Exception:
        pass
    return False, ""


def _mark_complete():
    s = st.session_state
    s.book_puzzle_status = "solved"
    progress = s.book_puzzle_progress
    key = str(s.book_puzzle_number)
    data = progress.get(key, {"solved": 0, "attempts": 0, "mistakes": 0})
    data["solved"] = int(data.get("solved", 0)) + 1
    data["attempts"] = int(data.get("attempts", 0)) + 1
    data["mistakes"] = int(data.get("mistakes", 0)) + s.book_puzzle_wrong
    data["last_solved_utc"] = datetime.now(timezone.utc).isoformat()
    data["solved_first_try"] = s.book_puzzle_wrong == 0
    progress[key] = data
    save_progress(progress)
    s.book_puzzle_notice = "Correct. Puzzle completed."


def strongest_stockfish_move(board, engine_path, think_seconds):
    """Play the top engine move without Elo/skill weakening or randomisation.

    Thinking time controls search depth in practice; it is not a strength cap.
    This is independent of the adjustable-rating opponent in the main app.
    """
    if not engine_path:
        raise FileNotFoundError("Stockfish is not configured.")
    if board.is_game_over():
        return None
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        options = {}
        if "UCI_LimitStrength" in engine.options:
            options["UCI_LimitStrength"] = False
        if "Skill Level" in engine.options:
            options["Skill Level"] = 20
        if "Threads" in engine.options:
            options["Threads"] = min(4, max(1, (os.cpu_count() or 2) - 1))
        if "Hash" in engine.options:
            options["Hash"] = 128
        if options:
            engine.configure(options)
        result = engine.play(board, chess.engine.Limit(time=float(think_seconds)))
        if result.move not in board.legal_moves:
            raise RuntimeError("The engine did not return a legal move.")
        return result.move


def _push_puzzle_move(board, move):
    st.session_state.book_puzzle_history.append(move.uci())
    board.push(move)
    st.session_state.book_puzzle_board_fen = board.fen()


def play_stockfish_reply(engine_path, think_seconds):
    """Finish an outstanding engine turn; keep the position on engine errors."""
    s = st.session_state
    board = chess.Board(s.book_puzzle_board_fen)
    p = BY_ID[s.book_puzzle_number]
    if board.is_game_over():
        s.book_puzzle_engine_pending = False
        s.book_puzzle_status = "finished"
        s.book_puzzle_notice += " The line has ended. Press Retry to solve the puzzle again."
        return
    if board.turn == (p["side"] == "white"):
        s.book_puzzle_engine_pending = False
        return
    s.book_puzzle_engine_pending = True
    try:
        reply = strongest_stockfish_move(board, engine_path, think_seconds)
    except (OSError, ValueError, RuntimeError, chess.engine.EngineError, chess.engine.EngineTerminatedError) as exc:
        s.book_puzzle_notice += f" Stockfish could not reply ({exc}). Check the engine path, then use 'Play Stockfish reply' or Retry."
        return
    if reply is None:
        s.book_puzzle_engine_pending = False
        s.book_puzzle_status = "finished"
        return
    reply_label = board.san(reply)
    _push_puzzle_move(board, reply)
    s.book_puzzle_engine_pending = False
    s.book_puzzle_notice += f" Stockfish's best reply: {reply_label}."
    if board.is_game_over():
        s.book_puzzle_status = "finished"
        s.book_puzzle_notice += " Game over — Retry to return to the puzzle."
    else:
        s.book_puzzle_notice += " Your turn — keep playing, or Retry the puzzle."


def play_move(move, engine_path, think_seconds=3):
    s = st.session_state
    if s.book_puzzle_status != "playing":
        return
    board = chess.Board(s.book_puzzle_board_fen)
    p = BY_ID[s.book_puzzle_number]
    if board.turn != (p["side"] == "white"):
        s.book_puzzle_notice = "Waiting for Stockfish. Use 'Play Stockfish reply' if needed."
        return
    if move not in board.legal_moves:
        s.book_puzzle_notice = "Illegal move — choose a legal square."
        return

    label = board.san(move)
    # After the first off-solution move, keep ALL subsequent legal moves.
    # Stockfish responds at full strength to each human move.
    if s.book_puzzle_branch == "stockfish":
        _push_puzzle_move(board, move)
        s.book_puzzle_notice = f"You played {label}."
        play_stockfish_reply(engine_path, think_seconds)
        return

    plan = s.book_puzzle_plan
    expected = chess.Move.from_uci(plan[s.book_puzzle_cursor]) if s.book_puzzle_cursor < len(plan) else None
    approved = expected == move
    alternate = False
    explanation = ""
    if not approved:
        alternate, explanation = engine_alternative(board, move, engine_path)
        approved = alternate

    if not approved:
        s.book_puzzle_wrong += 1
        s.book_puzzle_branch = "stockfish"
        _push_puzzle_move(board, move)
        s.book_puzzle_notice = f"{label} is legal, but it does not match the book's intended solution."
        play_stockfish_reply(engine_path, think_seconds)
        return

    _push_puzzle_move(board, move)
    s.book_puzzle_notice = f"Correct — {label}." + (" " + explanation if explanation else "")
    s.book_puzzle_last_info = explanation
    if alternate:
        _mark_complete()
        s.book_puzzle_notice = f"Good alternative: {label}. " + explanation
        return

    s.book_puzzle_cursor += 1
    # Keep the book's verified opponent continuation for correct solutions.
    if s.book_puzzle_cursor < len(plan):
        reply = chess.Move.from_uci(plan[s.book_puzzle_cursor])
        if reply in board.legal_moves and board.turn != (p["side"] == "white"):
            reply_label = board.san(reply)
            _push_puzzle_move(board, reply)
            s.book_puzzle_cursor += 1
            s.book_puzzle_notice += f" Book reply: {reply_label}. Find the next move."
    if s.book_puzzle_cursor >= len(plan) or board.is_game_over():
        _mark_complete()


def puzzle_move_history(puzzle, history):
    """Show the actual explored line in human-readable chess notation."""
    board = chess.Board(puzzle["fen"])
    labels = []
    for uci in history:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            break
        prefix = f"{board.fullmove_number}." if board.turn == chess.WHITE else f"{board.fullmove_number}..."
        labels.append(f"{prefix} {board.san(move)}")
        board.push(move)
    return "  ".join(labels)


def render_book_puzzle_mode(engine_path, board_component, piece_images, board_position_dict, legal_move_map):
    s = st.session_state
    if "book_puzzle_progress" not in s:
        s.book_puzzle_progress = read_progress()
    if "book_puzzle_number" not in s:
        start(1)
    # Provide defaults if code is reloaded while an older session is still open.
    if "book_puzzle_branch" not in s:
        s.book_puzzle_branch = "guided"
    if "book_puzzle_engine_pending" not in s:
        s.book_puzzle_engine_pending = False
    n = s.book_puzzle_number
    st.sidebar.divider()
    st.sidebar.subheader("Book practice")
    choice = st.sidebar.selectbox(
        "Choose puzzle", list(range(1, 101)), index=n - 1,
        format_func=lambda j: f"Puzzle {j:03} — {'500–800' if j <= 90 else '900–1200'}",
        key=f"book_puzzle_picker_{n}",
    )
    if choice != n:
        start(choice)
        st.rerun()
    solved = sum(1 for v in s.book_puzzle_progress.values() if v.get("solved", 0) > 0)
    st.sidebar.progress(solved / 100, text=f"{solved}/100 puzzles solved")
    st.sidebar.caption("Progress is saved locally to book_puzzles/progress.json.")
    think_seconds = st.sidebar.slider(
        "Stockfish thinking time (seconds)",
        min_value=1, max_value=20, value=3,
        help="Full strength (Skill 20, no Elo cap). More seconds = deeper calculation.",
        key="book_puzzle_think_seconds",
    )

    puzzle = BY_ID[n]
    board = chess.Board(s.book_puzzle_board_fen)
    st.title("The Thinking Method — Puzzle Practice")
    st.caption("Akeem Brown · Book 1: Foundations · 100 puzzles in the book's order")
    bar_left,bar_right = st.columns([3,1])
    with bar_left:
        st.subheader(f"Puzzle {n} of 100 · {puzzle['tier']}")
        st.caption(f"{puzzle['side'].title()} to move · PDF page {puzzle['page']}")
    with bar_right:
        st.metric("Moves off the book line", s.book_puzzle_wrong)
    if not engine_path:
        st.info("Stockfish was not found. Correct book moves still work, but wrong-move replies require the Stockfish executable. Set its path in the sidebar.")
    if s.book_puzzle_branch == "stockfish":
        st.info("**Play against Stockfish:** You left the book's solution. Every legal move now stays on the board, and Stockfish plays its strongest reply. Press Retry to restart the original puzzle.")
    if s.book_puzzle_parse_error:
        st.warning(s.book_puzzle_parse_error)
    if s.book_puzzle_notice:
        if s.book_puzzle_status == "solved":
            st.success(s.book_puzzle_notice)
        elif s.book_puzzle_notice.startswith("Correct"):
            st.info(s.book_puzzle_notice)
        else:
            st.warning(s.book_puzzle_notice)

    left,right=st.columns([1.45,0.85],gap="large")
    with left:
        allowed,movable=legal_move_map(board,puzzle["side"]=="white",False)
        if s.book_puzzle_status=="solved":
            allowed,movable={},[]
        last=s.book_puzzle_history[-1] if s.book_puzzle_history else ""
        board_widget=board_component(
            key="book_puzzle_chessboard",
            data={
                "position":board_position_dict(board),
                "evaluation":0.0,
                "arrows":[],
                "piece_images":piece_images,
                "orientation":puzzle["side"],
                "legal_moves":allowed,
                "movable_squares":movable,
                "user_turn":s.book_puzzle_status=="playing" and board.turn==(puzzle["side"]=="white"),
                "last_move":[last[:2],last[2:4]] if last else [],
                "pending_engine":False,
                "move_number":len(s.book_puzzle_history),
            },
            on_move_change=lambda: None,
            on_engine_move_change=lambda: None,
            width="stretch",height="content",
        )
        incoming=getattr(board_widget,"move",None)
        if incoming:
            nonce=incoming.get("nonce")
            if nonce != s.book_puzzle_last_nonce:
                s.book_puzzle_last_nonce=nonce
                from_sq=incoming.get("from");to_sq=incoming.get("to")
                if from_sq and to_sq:
                    a=chess.parse_square(from_sq);b=chess.parse_square(to_sq)
                    piece=board.piece_at(a)
                    promo = chess.QUEEN if piece and piece.piece_type==chess.PAWN and chess.square_rank(b) in (0,7) else None
                    play_move(chess.Move(a,b,promotion=promo),engine_path,think_seconds)
                    st.rerun()
        if s.book_puzzle_engine_pending:
            if st.button("Play Stockfish reply", use_container_width=True, type="primary"):
                s.book_puzzle_notice = "Retrying Stockfish's best move."
                play_stockfish_reply(engine_path, think_seconds)
                st.rerun()
        if s.book_puzzle_history:
            with st.expander("Moves played in this position"):
                st.write(puzzle_move_history(puzzle, s.book_puzzle_history))
        prev_col,next_col,restart_col=st.columns(3)
        with prev_col:
            if st.button("Previous",use_container_width=True,disabled=n<=1):
                start(n-1);st.rerun()
        with next_col:
            if st.button("Next puzzle",use_container_width=True,disabled=n>=100,type="primary"):
                start(n+1);st.rerun()
        with restart_col:
            if st.button("Retry",use_container_width=True):
                start(n);st.rerun()

    with right:
        st.markdown("#### Find the weakness")
        st.caption("First spot the weakness, then look for checks → captures → threats.")
        hints=[
            "King safety · Loose pieces · Pieces on the same line · Last-move drawback",
            "Attackers vs defenders · One defender · Overworked or pinned pieces",
            "King focal points · Pawn structure · X-rays · Misplaced pieces",
        ]
        st.markdown("**Hints**")
        if st.button("Give me a hint",disabled=s.book_puzzle_hint>=4,use_container_width=True):
            s.book_puzzle_hint+=1;st.rerun()
        if s.book_puzzle_hint>=1:
            st.info("Try to identify the position's biggest weakness before searching for forcing moves.")
        if s.book_puzzle_hint>=2:
            st.info("Book pattern: " + (puzzle.get("pattern") or "Check the 12 weakness categories."))
        if s.book_puzzle_hint>=3:
            st.info("The answer begins with a " + ("check" if puzzle["first_move"].endswith(("+","#")) else "forcing or improving move") + ".")
        if s.book_puzzle_hint>=4:
            st.info("Book first move: " + puzzle["first_move"])

        if s.book_puzzle_status=="solved":
            st.markdown("#### Book's explanation")
            st.write(puzzle["solution"])
            if puzzle["editor_note"]:
                st.caption("Notation clarification: " + puzzle["editor_note"])
            st.markdown("**What to remember**")
            st.write(puzzle.get("pattern") or "Identify the weakness before choosing a forcing move.")
        else:
            if st.button("Reveal answer",use_container_width=True):
                s.book_puzzle_solution=True;st.rerun()
            if s.book_puzzle_solution:
                st.warning("Book's intended first move: **" + puzzle["first_move"] + "**")
                with st.expander("Show full printed explanation"):
                    st.write(puzzle["solution"])
                    if puzzle["editor_note"]:st.caption(puzzle["editor_note"])
        with st.expander("Original book diagram (reference)"):
            st.image(str(BASE/f"{n:03d}.png"),use_container_width=True)
            st.caption("Diagram extracted from your uploaded PDF; White or Black is shown at the bottom as in the source.")
        with st.expander("How moves are graded"):
            st.write("Book-solution moves are marked correct and follow the printed line. Stockfish may also accept a strong alternative. Any other legal move is played on the board; Stockfish responds at full strength, and you can keep playing. Off-solution exploration does not count as solving the puzzle. Press Retry to return to the book position.")
