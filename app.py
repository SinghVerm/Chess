import base64
import json
import io
import random
import os
import shutil
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import chess.svg
import altair as alt
import pandas as pd
import streamlit as st

from book_review import BOOK_QUESTIONS, quick_move_review, review_pgn, deepen_move


st.set_page_config(page_title="Opening Trainer", page_icon="♟", layout="wide")

# ---------------------------------------------------------------------
# OPENINGS
# The opening only decides your colour. Stockfish plays every computer
# move from move 1, so you can play any line you like.
# ---------------------------------------------------------------------

OPENINGS = {
    "London System": {"user_color": chess.WHITE},
    "Caro-Kann": {"user_color": chess.BLACK},
}



# ---------------------------------------------------------------------
# CHESS.COM-STYLE INTERACTIVE BOARD
# Streamlit Components v2 lets JavaScript send drag/drop moves to Python.
# ---------------------------------------------------------------------

BOARD_HTML = """
<div class="board-layout">

    <div class="eval-bar">
        <div id="eval-black" class="eval-black"></div>
        <div id="eval-white" class="eval-white"></div>

        <div id="eval-text" class="eval-text">
            0.0
        </div>
    </div>

    <div class="board-shell">
        <div class="board-area">
            <div id="board"
                 class="chess-board"
                 aria-label="Chess board">
            </div>

            <svg
                id="arrow-layer"
                class="arrow-layer">
            </svg>
        </div>
    </div>

</div>
"""

BOARD_CSS = r"""
:host { display:block; width:100%; }

.board-layout {
    width: 100%;
    max-width: 758px;
    margin: 0 auto;
    display: flex;
    gap: 8px;
    align-items: stretch;
}

.eval-bar {
    position: relative;
    width: 30px;
    flex-shrink: 0;
    border-radius: 4px;
    overflow: hidden;
    background: #333;
}

.eval-white {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: #eeeeee;
    height: 50%;
    transition: height 350ms cubic-bezier(.2,.8,.2,1);
}

.eval-black {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    background: #333333;
    height: 50%;
}

.eval-text {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    bottom: 6px;

    font-size: 11px;
    font-weight: 700;

    color: #111;
    z-index: 10;
}

.board-shell { flex:1; min-width:0; max-width:720px; margin:0 auto; user-select:none; -webkit-user-select:none; }
.chess-board {
    width:100%; aspect-ratio:1/1; display:grid;
    grid-template-columns:repeat(8,1fr); grid-template-rows:repeat(8,1fr);
    overflow:hidden; border-radius:6px; background:#312e2b;
    box-shadow:0 2px 12px rgba(0,0,0,.22); touch-action:manipulation;
}
.square { position:relative; display:flex; align-items:center; justify-content:center; min-width:0; min-height:0; transition:background-color 180ms ease; }
.square.light { background:#bca17c; }
.square.dark { background:#74553b; }
.square.last.light { background:#c7a355; transition:background-color 220ms ease; }
.square.last.dark { background:#a37d35; transition:background-color 220ms ease; }
.square.selected { box-shadow:inset 0 0 0 5px rgba(246,246,105,.82); }
.square.legal-empty::after {
    content:""; width:24%; height:24%; border-radius:999px;
    background:rgba(0,0,0,.20); position:absolute; z-index:2;
}
.square.legal-capture::after {
    content:""; position:absolute; inset:4%; border-radius:999px;
    border:clamp(4px,.75vw,8px) solid rgba(0,0,0,.18); z-index:2;
}
.piece {
    width:88%; height:88%; object-fit:contain; position:relative; z-index:3;
    cursor:grab; -webkit-user-drag:element; filter:drop-shadow(0 1px 0 rgba(0,0,0,.10));
    transition:transform 180ms cubic-bezier(.2,.8,.2,1), opacity 120ms ease;
    will-change:transform;
}
.piece.moving { z-index:5; }
.piece:active { cursor:grabbing; }
.square.disabled .piece { cursor:default; }
.coord {
    position:absolute; z-index:4; font-size:clamp(9px,1.35vw,14px);
    font-weight:700; line-height:1; pointer-events:none;
}
.coord.file { right:4px; bottom:3px; }
.coord.rank { left:4px; top:3px; }
.square.light .coord { color:#74553b; }
.square.dark .coord { color:#bca17c; }
.square.last.light .coord { color:#74553b; }
.square.last.dark .coord { color:#bca17c; }
@media (max-width:640px) { .chess-board { border-radius:3px; } }

.board-area {
    position: relative;
    width: 100%;
    aspect-ratio: 1 / 1;
}

.arrow-layer {
    position: absolute;
    inset: 0;

    width: 100%;
    height: 100%;

    pointer-events: none;

    z-index: 20;
}

.arrow-line {
    stroke-linecap: round;
    opacity: 0.72;
}
"""

BOARD_JS = r"""
const boardStates = new WeakMap();

export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const board = parentElement.querySelector("#board");
    if (!board || !data) return;

    let state = boardStates.get(parentElement);
    if (!state) {
        state = { lastMoveNumber: -1, engineTimer: null, droppedMove: null };
        boardStates.set(parentElement, state);
    }

    const evalWhite = parentElement.querySelector("#eval-white");
    const evalText = parentElement.querySelector("#eval-text");

    function updateEvalBar() {
        if (!evalWhite || !evalText) return;

        const evaluation = Number(data.evaluation || 0);
        const score = Math.max(-10, Math.min(10, evaluation));

        // Map roughly -10...+10 pawns onto 0...100% white.
        const whitePercent = Math.max(0, Math.min(100, 50 + (score / 10) * 50));
        evalWhite.style.height = whitePercent + "%";

        if (evaluation >= 99) {
            evalText.textContent = "M";
        } else if (evaluation <= -99) {
            evalText.textContent = "-M";
        } else {
            const prefix = evaluation > 0 ? "+" : "";
            evalText.textContent = prefix + evaluation.toFixed(1);
        }

        // Put the text on whichever side has more room.
        if (whitePercent > 55) {
            evalText.style.bottom = "6px";
            evalText.style.top = "auto";
            evalText.style.color = "#111";
        } else {
            evalText.style.top = "6px";
            evalText.style.bottom = "auto";
            evalText.style.color = "#fff";
        }
    }

    const baseFiles = ["a","b","c","d","e","f","g","h"];
    const baseRanks = ["8","7","6","5","4","3","2","1"];
    const files = data.orientation === "black" ? [...baseFiles].reverse() : baseFiles;
    const ranks = data.orientation === "black" ? [...baseRanks].reverse() : baseRanks;

    let selected = null;
    let dragFrom = null;
    const targets = (from) => (data.legal_moves?.[from] || []);
    const movable = (sq) => Boolean(data.user_turn && data.movable_squares?.includes(sq));

    function sendMove(from, to) {
        if (!from || !to || from === to || !targets(from).includes(to)) return;
        setTriggerValue("move", {from:from, to:to, nonce:Date.now()});
    }

    function clickSquare(sq) {
        if (!data.user_turn) return;
        if (selected) {
            if (selected === sq) { selected = null; render(); return; }
            if (targets(selected).includes(sq)) { sendMove(selected, sq); return; }
            if (movable(sq)) { selected = sq; render(); return; }
            selected = null; render(); return;
        }
        if (movable(sq)) { selected = sq; render(); }
    }

    function render() {
        board.replaceChildren();
        for (const rank of ranks) {
            for (const file of files) {
                const sq = file + rank;
                const fi = file.charCodeAt(0) - 97;
                const ri = parseInt(rank, 10) - 1;
                const light = ((fi + ri) % 2) === 1;

                const el = document.createElement("div");
                el.className = "square " + (light ? "light" : "dark");
                el.dataset.square = sq;
                if (data.last_move?.includes(sq)) el.classList.add("last");
                if (selected === sq) el.classList.add("selected");
                if (!data.user_turn) el.classList.add("disabled");

                if (selected && targets(selected).includes(sq)) {
                    el.classList.add(data.position?.[sq] ? "legal-capture" : "legal-empty");
                }

                const symbol = data.position?.[sq];
                if (symbol) {
                    const img = document.createElement("img");
                    img.className = "piece";
                    img.src = data.piece_images[symbol];
                    img.alt = symbol;
                    img.draggable = movable(sq);
                    img.addEventListener("dragstart", (event) => {
                        if (!movable(sq)) { event.preventDefault(); return; }
                        dragFrom = sq; selected = sq;
                        if (event.dataTransfer) {
                            event.dataTransfer.effectAllowed = "move";
                            event.dataTransfer.setData("text/plain", sq);
                        }
                    });
                    img.addEventListener("dragend", () => { dragFrom = null; });
                    el.appendChild(img);
                }

                el.addEventListener("dragover", (event) => {
                    if (dragFrom && targets(dragFrom).includes(sq)) {
                        event.preventDefault();
                        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
                    }
                });
                el.addEventListener("drop", (event) => {
                    event.preventDefault();
                    const from = dragFrom || (event.dataTransfer ? event.dataTransfer.getData("text/plain") : "");
                    dragFrom = null;
                    if (from && targets(from).includes(sq)) {
                        // The piece is already where it was dropped, so don't slide it again.
                        state.droppedMove = from + sq;
                        sendMove(from, sq);
                    }
                    else { selected = null; render(); }
                });
                el.addEventListener("click", () => clickSquare(sq));

                const bottom = rank === ranks[ranks.length - 1];
                const left = file === files[0];
                if (bottom) {
                    const c = document.createElement("span");
                    c.className = "coord file"; c.textContent = file; el.appendChild(c);
                }
                if (left) {
                    const c = document.createElement("span");
                    c.className = "coord rank"; c.textContent = rank; el.appendChild(c);
                }

                board.appendChild(el);
            }
        }

        animateLastMove();
    }

    function animateLastMove() {
        const moveNumber = data.move_number ?? 0;
        // Only slide on new moves; take-backs and re-renders stay still.
        if (moveNumber <= state.lastMoveNumber) {
            state.lastMoveNumber = moveNumber;
            return;
        }
        state.lastMoveNumber = moveNumber;

        if (!data.last_move || data.last_move.length !== 2) return;
        const [from, to] = data.last_move;

        if (state.droppedMove === from + to) {
            state.droppedMove = null;
            return;
        }
        state.droppedMove = null;

        const fromSquare = board.querySelector(`[data-square="${from}"]`);
        const toSquare = board.querySelector(`[data-square="${to}"]`);
        const movedPiece = toSquare?.querySelector(".piece");
        if (!fromSquare || !toSquare || !movedPiece) return;

        const fromRect = fromSquare.getBoundingClientRect();
        const toRect = toSquare.getBoundingClientRect();
        const dx = fromRect.left - toRect.left;
        const dy = fromRect.top - toRect.top;

        movedPiece.classList.add("moving");
        movedPiece.style.transition = "none";
        movedPiece.style.transform = `translate(${dx}px, ${dy}px)`;
        movedPiece.getBoundingClientRect();

        requestAnimationFrame(() => {
            movedPiece.style.transition = "transform 180ms cubic-bezier(.2,.8,.2,1)";
            movedPiece.style.transform = "translate(0px, 0px)";
            movedPiece.addEventListener(
                "transitionend",
                () => movedPiece.classList.remove("moving"),
                { once: true },
            );
        });
    }

    function drawArrows() {
        const svg = parentElement.querySelector("#arrow-layer");
        if (!svg) return;

        svg.replaceChildren();

        const boardRect = board.getBoundingClientRect();
        if (!boardRect.width || !boardRect.height) return;

        svg.setAttribute("viewBox", `0 0 ${boardRect.width} ${boardRect.height}`);

        const colours = {
            best: "#56a84f",
            threat: "#e2a93b",
            check: "#e24a4a",
            mate: "#d633ff",
        };

        const svgNS = "http://www.w3.org/2000/svg";
        const squareSize = boardRect.width / 8;
        const strokeWidth = squareSize * 0.16;
        // Arrowhead length in stroke widths (marker uses strokeWidth units).
        const headLength = 3;

        const defs = document.createElementNS(svgNS, "defs");
        svg.appendChild(defs);

        for (const arrow of (data.arrows || [])) {
            const fromSquare = board.querySelector(`[data-square="${arrow.from}"]`);
            const toSquare = board.querySelector(`[data-square="${arrow.to}"]`);
            if (!fromSquare || !toSquare) continue;

            const fromRect = fromSquare.getBoundingClientRect();
            const toRect = toSquare.getBoundingClientRect();

            const x1 = fromRect.left - boardRect.left + fromRect.width / 2;
            const y1 = fromRect.top - boardRect.top + fromRect.height / 2;
            const x2 = toRect.left - boardRect.left + toRect.width / 2;
            const y2 = toRect.top - boardRect.top + toRect.height / 2;

            const dx = x2 - x1;
            const dy = y2 - y1;
            const length = Math.sqrt(dx * dx + dy * dy);
            if (!length) continue;

            // Stop the shaft so the arrowhead tip lands on the target centre.
            const shorten = (headLength / 2) * strokeWidth;
            const endX = x2 - (dx / length) * shorten;
            const endY = y2 - (dy / length) * shorten;

            const kind = colours[arrow.kind] ? arrow.kind : "best";
            const colour = colours[kind];
            const markerId = `arrowhead-${kind}`;

            if (!defs.querySelector(`#${markerId}`)) {
                const marker = document.createElementNS(svgNS, "marker");
                marker.setAttribute("id", markerId);
                marker.setAttribute("viewBox", "0 0 10 10");
                marker.setAttribute("markerWidth", String(headLength));
                marker.setAttribute("markerHeight", String(headLength));
                marker.setAttribute("refX", "5");
                marker.setAttribute("refY", "5");
                marker.setAttribute("orient", "auto");

                const path = document.createElementNS(svgNS, "path");
                path.setAttribute("d", "M0,0 L10,5 L0,10 z");
                path.setAttribute("fill", colour);

                marker.appendChild(path);
                defs.appendChild(marker);
            }

            const line = document.createElementNS(svgNS, "line");
            line.setAttribute("x1", x1);
            line.setAttribute("y1", y1);
            line.setAttribute("x2", endX);
            line.setAttribute("y2", endY);
            line.setAttribute("stroke", colour);
            line.setAttribute("stroke-width", strokeWidth);
            line.setAttribute("class", "arrow-line");
            line.setAttribute("marker-end", `url(#${markerId})`);

            svg.appendChild(line);
        }
    }

    updateEvalBar();
    render();

    requestAnimationFrame(() => {
        drawArrows();
    });

    if (state.engineTimer) {
        clearTimeout(state.engineTimer);
        state.engineTimer = null;
    }

    if (data.pending_engine) {
        state.engineTimer = setTimeout(() => {
            state.engineTimer = null;
            setTriggerValue("engine_move", { nonce: Date.now() });
        }, 350);
    }
}
"""

chessboard_component = st.components.v2.component(
    "opening_trainer_chessboard",
    html=BOARD_HTML,
    css=BOARD_CSS,
    js=BOARD_JS,
)


def reset_game(opening_name):
    st.session_state.active_opening = opening_name
    st.session_state.fen = chess.STARTING_FEN
    st.session_state.history = []
    st.session_state.selected_square = None
    st.session_state.notice = ""
    st.session_state.error = ""
    st.session_state.base_fen = chess.STARTING_FEN
    st.session_state.imported_mode = False
    st.session_state.imported_label = ""
    st.session_state.import_user_color = None
    st.session_state.imported_moves = []
    st.session_state.review_index = 0
    st.session_state.review_mode = False
    st.session_state.variation_mode = False
    st.session_state.variation_start_index = None
    st.session_state.variation_moves = []
    st.session_state.book_review_report = None
    st.session_state.coach_replay = None
    # When you play Black, Stockfish (White) has to open the game.
    st.session_state.pending_engine_move = OPENINGS[opening_name]["user_color"] == chess.BLACK


def current_user_color():
    if st.session_state.get("imported_mode", False):
        return st.session_state.import_user_color
    return OPENINGS[st.session_state.active_opening]["user_color"]


def parse_pgn_games(pgn_text):
    games = []
    stream = io.StringIO(pgn_text)
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        games.append(game)
    return games


def pgn_game_label(game, index):
    white = game.headers.get("White", "White")
    black = game.headers.get("Black", "Black")
    date = game.headers.get("Date", "")
    label = f"{index + 1}. {white} vs {black}"
    if date:
        label += f" · {date}"
    return label


def start_imported_game(board, play_as, label):
    user_color = chess.WHITE if play_as == "White" else chess.BLACK
    st.session_state.fen = board.fen()
    st.session_state.selected_square = None
    st.session_state.imported_mode = True
    st.session_state.imported_label = label
    st.session_state.import_user_color = user_color
    st.session_state.pending_engine_move = (
        not board.is_game_over() and board.turn != user_color
    )
    st.session_state.notice = f"Loaded {label}."


def load_pgn_game(game, play_as):
    st.session_state.book_review_report = None
    start_board = game.board()
    moves = []
    board = start_board.copy()

    for move in game.mainline_moves():
        moves.append(move.uci())
        board.push(move)

    st.session_state.base_fen = start_board.fen()
    st.session_state.imported_moves = moves

    # Open at the end of the imported game
    st.session_state.review_index = len(moves)
    st.session_state.review_mode = True
    clear_variation()

    st.session_state.history = moves.copy()
    st.session_state.fen = board.fen()
    st.session_state.selected_square = None

    st.session_state.imported_mode = True
    st.session_state.import_user_color = (
        chess.WHITE if play_as == "White" else chess.BLACK
    )

    white = game.headers.get("White", "White")
    black = game.headers.get("Black", "Black")
    st.session_state.imported_label = f"{white} vs {black}"

    # Very important: don't let Stockfish move while reviewing
    st.session_state.pending_engine_move = False

    st.session_state.notice = "Imported game loaded."
    st.session_state.error = ""


def clear_variation():
    st.session_state.variation_mode = False
    st.session_state.variation_start_index = None
    st.session_state.variation_moves = []
    st.session_state.coach_replay = None


def show_coach_replay_position(step_index):
    """Display a Stockfish variation on the normal board, without altering PGN."""
    replay = st.session_state.get("coach_replay")
    if not replay:
        return
    index = max(0, min(step_index, len(replay["steps"])))
    board = chess.Board(st.session_state.base_fen)
    prefix = st.session_state.imported_moves[:replay["start_index"]]
    for uci in prefix:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError("Imported game differs from the replay origin.")
        board.push(move)
    followed = []
    for step in replay["steps"][:index]:
        move = chess.Move.from_uci(step["uci"])
        if move not in board.legal_moves:
            raise ValueError("Engine continuation contains an illegal move.")
        board.push(move)
        followed.append(move.uci())
    replay["index"] = index
    st.session_state.fen = board.fen()
    st.session_state.history = prefix + followed
    st.session_state.selected_square = None
    st.session_state.pending_engine_move = False
    st.session_state.error = ""
    st.session_state.notice = ""


def start_coach_replay(ply, branch, record):
    """The replay starts BEFORE the reviewed move and advances legally."""
    steps = record.get("played_steps" if branch == "played" else "better_steps") or []
    if not steps or ply < 1:
        return False
    clear_variation()
    st.session_state.coach_replay = {
        "ply": ply,
        "start_index": ply - 1,
        "branch": branch,
        "steps": steps,
        "index": 0,
    }
    show_coach_replay_position(1)
    return True


def go_to_imported_move(index):
    moves = st.session_state.imported_moves
    index = max(0, min(index, len(moves)))

    board = chess.Board(st.session_state.base_fen)
    for uci in moves[:index]:
        board.push(chess.Move.from_uci(uci))

    # Navigating the game always leaves any exploratory branch.
    clear_variation()

    st.session_state.review_index = index
    st.session_state.history = moves[:index].copy()
    st.session_state.fen = board.fen()
    st.session_state.pending_engine_move = False
    st.session_state.error = ""
    st.session_state.notice = ""


def start_variation_move(from_name, to_name):
    board = board_from_state()

    source = chess.parse_square(from_name)
    target = chess.parse_square(to_name)

    piece = board.piece_at(source)
    if piece is None:
        return False

    promotion = None
    if piece.piece_type == chess.PAWN:
        target_rank = chess.square_rank(target)
        if target_rank in (0, 7):
            promotion = chess.QUEEN

    move = chess.Move(
        source,
        target,
        promotion=promotion
    )

    if move not in board.legal_moves:
        return False

    san = board.san(move)

    if not st.session_state.get("variation_mode", False):
        st.session_state.variation_mode = True
        st.session_state.variation_start_index = (
            st.session_state.review_index
        )
        st.session_state.variation_moves = []

    st.session_state.variation_moves.append(move.uci())
    push_move(board, move)

    st.session_state.selected_square = None
    st.session_state.pending_engine_move = False
    st.session_state.notice = f"Analysis: {san}"
    st.session_state.error = ""
    return True


def return_to_game():
    original_index = st.session_state.variation_start_index
    clear_variation()
    go_to_imported_move(original_index)


def variation_start_fen():
    board = chess.Board(st.session_state.base_fen)
    for uci in st.session_state.imported_moves[:st.session_state.variation_start_index]:
        board.push(chess.Move.from_uci(uci))
    return board.fen()


def variation_origin_label():
    index = st.session_state.variation_start_index
    if not index:
        return "the starting position"

    board = chess.Board(st.session_state.base_fen)
    moves = st.session_state.imported_moves
    for uci in moves[:index - 1]:
        board.push(chess.Move.from_uci(uci))

    last = chess.Move.from_uci(moves[index - 1])
    dots = "." if board.turn == chess.WHITE else "..."
    return f"{board.fullmove_number}{dots} {board.san(last)}"


def play_from_review_position():
    st.session_state.review_mode = False
    clear_variation()

    # The current reviewed position now becomes the game
    st.session_state.base_fen = st.session_state.fen
    st.session_state.history = []
    st.session_state.selected_square = None

    board = board_from_state()
    st.session_state.pending_engine_move = (
        board.turn != st.session_state.import_user_color
        and not board.is_game_over()
    )
    st.session_state.notice = "Playing from this position."
    st.session_state.error = ""


def imported_move_rows():
    board = chess.Board(st.session_state.base_fen)
    moves = st.session_state.imported_moves

    rows = []
    white_move = ""
    white_index = None

    for i, uci in enumerate(moves):
        move = chess.Move.from_uci(uci)
        san = board.san(move)
        move_number = board.fullmove_number
        color = board.turn
        board.push(move)

        if color == chess.WHITE:
            white_move = san
            white_index = i + 1
        else:
            rows.append({
                "number": move_number,
                "white": white_move,
                "white_index": white_index,
                "black": san,
                "black_index": i + 1,
            })
            white_move = ""
            white_index = None

    if white_move:
        rows.append({
            "number": board.fullmove_number,
            "white": white_move,
            "white_index": white_index,
            "black": "",
            "black_index": None,
        })

    return rows


def load_fen_position(fen, play_as):
    st.session_state.book_review_report = None
    try:
        board = chess.Board(fen.strip())
    except ValueError as exc:
        st.session_state.error = f"Invalid FEN: {exc}"
        return
    if not board.is_valid():
        st.session_state.error = "That FEN is not a legal position."
        return

    st.session_state.base_fen = board.fen()
    st.session_state.history = []
    st.session_state.imported_moves = []
    st.session_state.review_index = 0
    st.session_state.review_mode = False
    clear_variation()
    st.session_state.error = ""
    start_imported_game(board, play_as, "Imported position")


def take_back():
    history = st.session_state.history
    user_color = current_user_color()

    board = chess.Board(
        st.session_state.get(
            "base_fen",
            chess.STARTING_FEN
        )
    )

    # Move i was played by the side to move in base_fen when i is even.
    first_mover = board.turn
    user_moves = [i for i in range(len(history)) if (i % 2 == 0) == (first_mover == user_color)]
    if not user_moves:
        return

    # Undo Stockfish's reply (if any) and your last move.
    del history[user_moves[-1]:]

    for uci in history:
        board.push(chess.Move.from_uci(uci))

    st.session_state.fen = board.fen()
    st.session_state.selected_square = None
    st.session_state.pending_engine_move = False
    st.session_state.notice = "Last move taken back."
    st.session_state.error = ""


def board_from_state():
    return chess.Board(st.session_state.fen)


def push_move(board, move):
    st.session_state.history.append(move.uci())
    board.push(move)
    st.session_state.fen = board.fen()


def move_history_text(history):
    board = chess.Board(
        st.session_state.get(
            "base_fen",
            chess.STARTING_FEN
        )
    )
    first_move_no = board.fullmove_number
    san_moves = ["…"] if board.turn == chess.BLACK and history else []

    for uci in history:
        move = chess.Move.from_uci(uci)
        san_moves.append(board.san(move))
        board.push(move)

    rows = []
    for i in range(0, len(san_moves), 2):
        move_no = first_move_no + i // 2
        white = san_moves[i]
        black = san_moves[i + 1] if i + 1 < len(san_moves) else ""
        rows.append(f"{move_no}. {white} {black}".strip())

    return "   ".join(rows) if rows else "No moves yet."


def auto_find_stockfish():
    """Find the correct executable for Windows desktop or Linux Streamlit Cloud."""
    base = Path(__file__).resolve().parent
    if os.name != "nt":
        # Debian's apt package usually installs Stockfish at /usr/games/stockfish,
        # which is not always included in the Streamlit Cloud PATH.
        for candidate in (
            shutil.which("stockfish"),
            "/usr/games/stockfish",
            "/usr/bin/stockfish",
            str(base / "stockfish"),
        ):
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return ""

    for pattern in ("stockfish*.exe", "stockfish/**/stockfish*.exe"):
        for item in base.glob(pattern):
            if item.is_file():
                return str(item)

    return shutil.which("stockfish") or ""


def stockfish_move(board, engine_path, rating):
    """
    For 1320+ use Stockfish's official UCI_Elo limiter.
    Below 1320 use Skill Level 0 plus a wider MultiPV choice to make
    the opponent more fallible. This is an approximation, not a direct
    Chess.com rating conversion.
    """
    if not engine_path:
        raise FileNotFoundError(
            "Stockfish was not found. Put the Stockfish executable in a "
            "'stockfish' folder beside app.py, or enter its path in the sidebar."
        )

    engine_file = Path(engine_path)
    if not engine_file.exists() and not shutil.which(engine_path):
        raise FileNotFoundError(f"Stockfish not found at: {engine_path}")

    engine = chess.engine.SimpleEngine.popen_uci(engine_path)

    try:
        if rating >= 1320:
            engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": min(int(rating), 3190),
            })
            result = engine.play(board, chess.engine.Limit(time=0.20))
            return result.move

        # Stockfish's built-in UCI_Elo floor is 1320.
        # For lower training ratings, deliberately choose among several
        # engine candidates instead of always taking the top move.
        engine.configure({
            "UCI_LimitStrength": False,
            "Skill Level": 0,
        })

        candidate_count = min(8, board.legal_moves.count())
        if candidate_count <= 1:
            return next(iter(board.legal_moves))

        infos = engine.analyse(
            board,
            chess.engine.Limit(depth=8),
            multipv=candidate_count,
        )

        candidates = []
        for info in infos:
            pv = info.get("pv", [])
            if pv:
                candidates.append(pv[0])

        if not candidates:
            return engine.play(board, chess.engine.Limit(time=0.10)).move

        # 800 -> broad choice, 1300 -> much closer to the top engine choices.
        strength = max(800, min(1319, int(rating)))
        spread = round(8 - ((strength - 800) / 519) * 5)
        spread = max(3, min(len(candidates), spread))
        candidates = candidates[:spread]

        # Best candidate remains most likely, but weaker settings sometimes
        # choose lower-ranked candidate moves.
        weights = list(range(spread, 0, -1))
        return random.choices(candidates, weights=weights, k=1)[0]

    finally:
        engine.quit()


def score_to_pawns(score):
    """White-POV score in pawns, with mates pinned to +/-100."""
    if score.is_mate():
        mate = score.mate()
        if mate is None or mate == 0:
            return 0.0
        return 100.0 if mate > 0 else -100.0
    cp = score.score()
    return 0.0 if cp is None else cp / 100.0


def analyse_position(board, engine_path, show_threat=True):
    """
    Evaluation, mate info and arrows in one Stockfish session.
    "evaluation" is in pawns and "mate" is in moves, both from White's
    point of view (positive = good for White).
    """
    return _analyse_fen(board.fen(), engine_path, show_threat)


@st.cache_data(show_spinner=False, max_entries=500)
def _analyse_fen(fen, engine_path, show_threat):
    board = chess.Board(fen)

    result = {
        "evaluation": 0.0,
        "arrows": [],
        "mate": None,
        "check": board.is_check(),
        "checkmate": board.is_checkmate(),
    }

    # Exact check arrows - no Stockfish needed
    if board.is_check():
        king_square = board.king(board.turn)
        if king_square is not None:
            attackers = board.attackers(not board.turn, king_square)
            for attacker in attackers:
                result["arrows"].append({
                    "from": chess.square_name(attacker),
                    "to": chess.square_name(king_square),
                    "kind": "check",
                })

    if board.is_checkmate():
        result["evaluation"] = -100.0 if board.turn == chess.WHITE else 100.0
        return result

    if board.is_game_over() or not engine_path:
        return result

    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    except Exception:
        return result

    try:
        # Main Stockfish analysis
        info = engine.analyse(board, chess.engine.Limit(depth=14))
        score = info["score"]

        result["evaluation"] = score_to_pawns(score.white())
        result["mate"] = score.white().mate()

        pv = info.get("pv", [])
        if pv:
            best = pv[0]
            mating = (score.relative.mate() or 0) > 0
            result["arrows"].append({
                "from": chess.square_name(best.from_square),
                "to": chess.square_name(best.to_square),
                "kind": "mate" if mating else "best",
            })

        # Threat: what would the opponent play if the side to move passed?
        # A null move is illegal while in check, so skip it then.
        if show_threat and not board.is_check():
            passed = board.copy(stack=False)
            passed.turn = not passed.turn
            passed.ep_square = None

            if not passed.is_game_over():
                threat_info = engine.analyse(passed, chess.engine.Limit(depth=10))
                threat_pv = threat_info.get("pv", [])
                if threat_pv:
                    threat = threat_pv[0]
                    threat_mates = (threat_info["score"].relative.mate() or 0) > 0
                    result["arrows"].append({
                        "from": chess.square_name(threat.from_square),
                        "to": chess.square_name(threat.to_square),
                        "kind": "mate" if threat_mates else "threat",
                    })

    except Exception:
        pass

    finally:
        try:
            engine.quit()
        except Exception:
            pass

    return result


def computer_turn(board, user_color):
    return board.turn != user_color


@st.cache_data(show_spinner=False, max_entries=20)
def imported_game_evals(base_fen, moves, engine_path):
    """White-POV eval in pawns for the start position and after every move."""
    board = chess.Board(base_fen)
    labels = ["Start"]
    evals = []

    engine = None
    if engine_path:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        except Exception:
            engine = None

    try:
        for i in range(len(moves) + 1):
            if board.is_checkmate():
                evals.append(-100.0 if board.turn == chess.WHITE else 100.0)
            elif board.is_game_over() or engine is None:
                evals.append(0.0)
            else:
                try:
                    info = engine.analyse(board, chess.engine.Limit(depth=10))
                    evals.append(score_to_pawns(info["score"].white()))
                except Exception:
                    evals.append(0.0)

            if i < len(moves):
                move = chess.Move.from_uci(moves[i])
                prefix = f"{board.fullmove_number}." if board.turn == chess.WHITE else f"{board.fullmove_number}..."
                labels.append(f"{prefix} {board.san(move)}")
                board.push(move)
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass

    return evals, labels


def eval_graph(evals, labels, current, base_fen):
    LIMIT = 6.0

    clamped = [
        max(-LIMIT, min(LIMIT, e))
        for e in evals
    ]

    # Work out whether each move was played by White or Black.
    start_board = chess.Board(base_fen)
    first_turn = start_board.turn

    qualities = ["start"]
    losses = [0.0]

    for i in range(1, len(evals)):
        before = evals[i - 1]
        after = evals[i]

        # i=1 means first move after starting position.
        mover_is_white = (
            first_turn == chess.WHITE
            if (i - 1) % 2 == 0
            else first_turn != chess.WHITE
        )

        # Positive = evaluation got worse for the player who moved.
        if mover_is_white:
            loss = before - after
        else:
            loss = after - before

        loss = max(0.0, loss)
        losses.append(loss)

        # Approximate categories for now.
        # These are NOT Chess.com's proprietary classifications.
        if loss <= 0.10:
            quality = "best"
        elif loss <= 0.30:
            quality = "good"
        elif loss <= 0.80:
            quality = "inaccuracy"
        elif loss <= 1.50:
            quality = "mistake"
        else:
            quality = "blunder"

        qualities.append(quality)

    df = pd.DataFrame({
        "ply": list(range(len(evals))),
        "eval": clamped,
        "actual_eval": evals,
        "move": labels,
        "quality": qualities,
        "loss": losses,
    })

    df["shown"] = [
        ("M" if e > 0 else "-M")
        if abs(e) >= 99
        else f"{e:+.1f}"
        for e in evals
    ]

    x_scale = alt.Scale(
        domain=[0, max(1, len(evals) - 1)],
        nice=False
    )

    y_scale = alt.Scale(
        domain=[-LIMIT, LIMIT],
        nice=False
    )

    # White evaluation area, similar to Chess.com.
    area = alt.Chart(df).mark_area(
        color="#f2f2f2",
        opacity=1,
        interpolate="linear",
        line={
            "color": "#d7d7d7",
            "strokeWidth": 1.5
        }
    ).encode(
        x=alt.X(
            "ply:Q",
            axis=None,
            scale=x_scale
        ),
        y=alt.Y(
            "eval:Q",
            axis=None,
            scale=y_scale
        ),
        y2=alt.datum(-LIMIT)
    )

    # 0.0 centre line.
    zero = alt.Chart(
        pd.DataFrame({"eval": [0]})
    ).mark_rule(
        color="#aaaaaa",
        strokeWidth=1.3
    ).encode(
        y=alt.Y(
            "eval:Q",
            scale=y_scale
        )
    )

    # Colored move-quality dots.
    dots = alt.Chart(
        df[df["ply"] > 0]
    ).mark_point(
        filled=True,
        size=58,
        stroke="#444444",
        strokeWidth=0.5
    ).encode(
        x=alt.X(
            "ply:Q",
            axis=None,
            scale=x_scale
        ),
        y=alt.Y(
            "eval:Q",
            axis=None,
            scale=y_scale
        ),

        color=alt.Color(
            "quality:N",
            scale=alt.Scale(
                domain=[
                    "best",
                    "good",
                    "inaccuracy",
                    "mistake",
                    "blunder"
                ],
                range=[
                    "#73a7c7",   # blue
                    "#70a94f",   # green
                    "#f3a14b",   # orange
                    "#f07445",   # orange/red
                    "#e75245",   # red
                ]
            ),
            legend=None
        ),

        tooltip=[
            alt.Tooltip(
                "move:N",
                title="Move"
            ),
            alt.Tooltip(
                "shown:N",
                title="Eval"
            ),
            alt.Tooltip(
                "quality:N",
                title="Quality"
            ),
            alt.Tooltip(
                "loss:Q",
                title="Eval loss",
                format=".2f"
            ),
        ]
    )

    # Vertical current-position line.
    current_line = alt.Chart(
        pd.DataFrame({
            "ply": [current]
        })
    ).mark_rule(
        color="#e5a72f",
        strokeWidth=2.5
    ).encode(
        x=alt.X(
            "ply:Q",
            scale=x_scale
        )
    )

    # Highlight current move's dot.
    current_df = df[
        df["ply"] == current
    ]

    current_dot = alt.Chart(
        current_df
    ).mark_point(
        filled=True,
        size=110,
        color="#e5a72f",
        stroke="#ffffff",
        strokeWidth=1
    ).encode(
        x=alt.X(
            "ply:Q",
            axis=None,
            scale=x_scale
        ),
        y=alt.Y(
            "eval:Q",
            axis=None,
            scale=y_scale
        )
    )

    return (
        alt.layer(
            area,
            zero,
            dots,
            current_line,
            current_dot,
        )
        .properties(
            height=125,
            background="#3b3b3b",
            padding=0
        )
        .configure_view(
            strokeWidth=0
        )
    )


def make_computer_move(engine_path, rating):
    board = board_from_state()

    if board.is_game_over():
        return False

    move = stockfish_move(board, engine_path, rating)
    san = board.san(move)
    push_move(board, move)
    st.session_state.notice = f"Stockfish played {san}"
    st.session_state.error = ""
    return True


def try_user_move(source, target):
    board = board_from_state()
    user_color = current_user_color()

    if board.turn != user_color:
        st.session_state.error = "It is not your turn."
        return False

    piece = board.piece_at(source)
    if piece is None or piece.color != user_color:
        st.session_state.error = "Select one of your own pieces first."
        return False

    # Auto-promote to queen for now.
    promotion = None
    if piece.piece_type == chess.PAWN:
        target_rank = chess.square_rank(target)
        if target_rank in (0, 7):
            promotion = chess.QUEEN

    move = chess.Move(source, target, promotion=promotion)

    if move not in board.legal_moves:
        st.session_state.error = "That is not a legal move."
        return False

    san = board.san(move)
    push_move(board, move)
    st.session_state.pending_engine_move = True
    st.session_state.notice = f"You played {san}"
    st.session_state.error = ""
    return True


def click_square(square):
    board = board_from_state()
    user_color = current_user_color()

    if board.is_game_over() or board.turn != user_color:
        return

    selected = st.session_state.selected_square

    if selected is None:
        piece = board.piece_at(square)
        if piece is None or piece.color != user_color:
            st.session_state.error = "Select one of your own pieces."
            return

        st.session_state.selected_square = square
        st.session_state.error = ""
        return

    if selected == square:
        st.session_state.selected_square = None
        return

    # Clicking another friendly piece simply changes the selected piece.
    target_piece = board.piece_at(square)
    if target_piece is not None and target_piece.color == user_color:
        st.session_state.selected_square = square
        st.session_state.error = ""
        return

    try_user_move(selected, square)
    st.session_state.selected_square = None


def result_message(board):
    if board.is_checkmate():
        winner = "Black" if board.turn == chess.WHITE else "White"
        return f"Checkmate — {winner} wins."

    if board.is_stalemate():
        return "Draw by stalemate."

    if board.is_insufficient_material():
        return "Draw by insufficient material."

    if board.can_claim_threefold_repetition():
        return "Threefold repetition can be claimed."

    if board.can_claim_fifty_moves():
        return "Fifty-move draw can be claimed."

    return ""




def piece_image_map():
    images = {}
    for symbol in "PNBRQKpnbrqk":
        piece = chess.Piece.from_symbol(symbol)
        svg = chess.svg.piece(piece, size=128)
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        images[symbol] = f"data:image/svg+xml;base64,{encoded}"
    return images


PIECE_IMAGES = piece_image_map()


def board_position_dict(board):
    return {
        chess.square_name(square): piece.symbol()
        for square, piece in board.piece_map().items()
    }


def legal_move_map(board, user_color=None, analysis_mode=False):
    if board.is_game_over():
        return {}, []

    # During imported-game analysis,
    # allow whichever side is currently to move.
    if not analysis_mode:
        if board.turn != user_color:
            return {}, []

    mapping = {}
    movable = set()

    for move in board.legal_moves:
        from_name = chess.square_name(move.from_square)
        to_name = chess.square_name(move.to_square)
        mapping.setdefault(from_name, [])
        if to_name not in mapping[from_name]:
            mapping[from_name].append(to_name)
        movable.add(from_name)

    return mapping, sorted(movable)


def move_history_rows(history, start_fen=None):
    board = chess.Board(
        start_fen or st.session_state.get(
            "base_fen",
            chess.STARTING_FEN
        )
    )
    first_move_no = board.fullmove_number
    sans = ["…"] if board.turn == chess.BLACK and history else []
    for uci in history:
        move = chess.Move.from_uci(uci)
        sans.append(board.san(move))
        board.push(move)

    rows = []
    for i in range(0, len(sans), 2):
        rows.append((first_move_no + i // 2, sans[i], sans[i + 1] if i + 1 < len(sans) else ""))
    return rows

# ---------------------------------------------------------------------
# IMPORTED-GAME BOOK REVIEW & NARRATION
# ---------------------------------------------------------------------

def narration_audio_control(narration):
    """Optional browser text-to-speech; speech begins only after a click."""
    spoken_text = json.dumps(narration).replace("<", "\\u003c")
    st.components.v1.html(
        f"""
        <div style="font-family:Arial,sans-serif;display:flex;gap:9px;align-items:center">
          <button id="speak" style="cursor:pointer;padding:7px 12px;border-radius:6px;border:1px solid #777;background:#333;color:white">▶ Listen</button>
          <button id="stop" style="cursor:pointer;padding:7px 12px;border-radius:6px;border:1px solid #777;background:#444;color:white">■ Stop</button>
          <span id="note" style="color:gray;font-size:12px"></span>
        </div>
        <script>
          const narration = {spoken_text};
          const synth = window.speechSynthesis;
          const note = document.getElementById('note');
          if (!synth) note.textContent = 'Speech not supported by this browser.';
          document.getElementById('speak').onclick = () => {{
            if (!synth) return;
            synth.cancel();
            const speech = new SpeechSynthesisUtterance(narration);
            speech.lang = 'en-AU';
            speech.rate = 0.95;
            synth.speak(speech);
          }};
          document.getElementById('stop').onclick = () => {{ if (synth) synth.cancel(); }};
        </script>
        """,
        height=47,
        scrolling=False,
    )


def show_imported_book_review(engine_path, user_color):
    """Always narrate the selected PGN move, even before engine review runs."""
    moves = st.session_state.imported_moves
    current = st.session_state.review_index
    base_fen = st.session_state.base_fen
    profile = st.selectbox(
        "Review detail",
        ["Quick", "Standard", "Thorough"],
        index=1,
        key="book_review_profile",
        help="Standard evaluates each game position for up to 0.20 seconds. Thorough takes longer and is generally more reliable.",
    )
    seconds = {"Quick": 0.08, "Standard": 0.20, "Thorough": 0.65}[profile]
    identity = (base_fen, tuple(moves), engine_path, profile)

    if st.button("Analyse uploaded game — all 12 weaknesses", use_container_width=True,
                 type="primary", key="book_analyse_game", disabled=not bool(moves)):
        with st.spinner("Stockfish is reviewing every move and the 12 weakness categories…"):
            try:
                report = review_pgn(base_fen, tuple(moves), engine_path, seconds)
                st.session_state.book_review_report = {"identity": identity, "report": report}
            except Exception as exc:
                st.session_state.book_review_report = None
                st.error(f"Could not review this game: {exc}")

    state = st.session_state.get("book_review_report")
    report = state["report"] if state and state.get("identity") == identity else None
    if report is not None:
        if report["engine_error"]:
            st.warning("Stockfish could not score moves: " + report["engine_error"])
        else:
            st.caption(f"Engine-scored {report['scored']} of {len(moves)} moves. "
                       f"Detected {len(report['alerts'])} significant evaluation drops across both sides.")

    if report is not None and current > 0:
        current_row = report["records"][current - 1]
    else:
        current_row = quick_move_review(base_fen, moves, current)

    st.markdown("#### Move explanation & narration")
    if st.session_state.get("variation_mode"):
        st.caption("This narration describes the selected original PGN move, not the exploratory variation.")
    if current_row.get("sections"):
        for label, description in current_row["sections"].items():
            st.markdown(f"**{label}:** {description}")
    else:
        st.write(current_row["narration"])
    narration_audio_control(current_row["narration"])

    # Genuine two-branch engine replay: both lines begin before the reviewed move.
    if report is not None and current > 0:
        st.markdown("##### Replay Stockfish's analysis on the board")
        played_steps = current_row.get("played_steps") or []
        better_steps = current_row.get("better_steps") or []
        col_p, col_b = st.columns(2)
        with col_p:
            if st.button("▶ Your move + reply", key="coach_played", use_container_width=True,
                         disabled=not played_steps):
                if start_coach_replay(current, "played", current_row):
                    st.rerun()
        with col_b:
            if st.button("▶ Better move + reply", key="coach_better", use_container_width=True,
                         disabled=not better_steps):
                if start_coach_replay(current, "better", current_row):
                    st.rerun()

        replay = st.session_state.get("coach_replay")
        if replay and replay.get("ply") == current:
            steps = replay["steps"]
            index = replay["index"]
            label = "Your move" if replay["branch"] == "played" else "Better alternative"
            st.caption(f"{label} · Step {index} of {len(steps)}. The main board shows this exact position.")
            if index:
                current_step = steps[index - 1]
                st.markdown(f"**{current_step['label']}** — {current_step['note']}")
                narration_audio_control(current_step["note"])
            else:
                st.write("Position before the move; inspect the threats before proceeding.")
            previous_col, next_col, exit_col = st.columns(3)
            with previous_col:
                if st.button("◀ Back", key="coach_back", use_container_width=True,
                             disabled=index == 0):
                    show_coach_replay_position(index - 1)
                    st.rerun()
            with next_col:
                if st.button("Next ▶", key="coach_next", use_container_width=True,
                             disabled=index >= len(steps)):
                    show_coach_replay_position(index + 1)
                    st.rerun()
            with exit_col:
                if st.button("↩ Exit replay", key="coach_exit", use_container_width=True):
                    go_to_imported_move(current)
                    st.rerun()
            st.caption("Replay moves come from Stockfish's principal variation, not a manually invented example. "
                       "A principal variation is one possible best-play line and may change at greater search depth.")
        else:
            st.caption("Choose either line to step through it on the main chessboard. "
                       "The original uploaded game remains unchanged.")

        if st.button("Re-analyse this move deeply", key="coach_deepen", use_container_width=True,
                     help="Spends about 2 seconds per position on the selected move and its actual result."):
            with st.spinner("Checking both continuations at greater depth…"):
                try:
                    new_row = deepen_move(base_fen, moves, current, engine_path, 2.0)
                    report["records"][current - 1] = new_row
                    kinds = ("Inaccuracy", "Mistake", "Blunder", "Missed forced mate", "Allowed forced mate")
                    report["alerts"] = [r for r in report["records"] if r["quality"] in kinds]
                    report["scored"] = sum(r["loss_cp"] is not None for r in report["records"])
                    go_to_imported_move(current)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Deep analysis failed: {exc}")
        if current_row.get("deepened"):
            st.caption("This move was individually re-analysed at higher search effort.")

    if report is not None and current > 0:
        # Hide raw engine notation by default: useful evidence for advanced
        # review, but a poor substitute for an actual chess explanation.
        with st.expander("Engine lines and numerical score (optional)", expanded=False):
            loss = current_row.get("loss_cp")
            if loss is not None:
                st.caption(f"Evaluation change: approximately {loss / 100:.1f} pawn units "
                           "(not necessarily material lost).")
            if current_row.get("played_line"):
                st.write("After the move played: " + current_row["played_line"])
            if current_row.get("best_line"):
                st.write("After Stockfish's alternative: " + current_row["best_line"])

    if current > 0 and current_row["quality"] in (
        "Blunder", "Mistake", "Inaccuracy", "Missed forced mate", "Allowed forced mate"
    ):
        st.warning(f"{current_row['label']}: {current_row['quality']} — "
                   f"Stockfish prefers {current_row.get('best_san') or 'a different continuation'}.")

    with st.expander("12 weakness questions — before this move", expanded=False):
        st.caption("In the book's original order. Patterns are training prompts, NOT explanations of the blunder. 'Not flagged' does not mean safe.")
        for item in current_row["before_scan"]:
            status = "Pattern found" if item["detected"] else "Not flagged"
            st.markdown(f"**{item['number']}. {item['name']}** — {item['question']}  ")
            if item["examples"]:
                st.caption("; ".join(item["examples"]))
            else:
                st.caption(status)
        st.markdown("**Then:** Checks → Captures → Threats. If no tactic exists, improve your least active piece.")

    if current > 0:
        after_found = [x for x in current_row.get("after_scan", []) if x["detected"]]
        if after_found:
            with st.expander("What your move left for the opponent", expanded=False):
                for item in after_found[:6]:
                    st.write(f"{item['number']}. {item['name']}: {item['examples'][0]}")

    if report is not None:
        st.markdown("#### Missed chances")
        include_both = st.toggle("Include opponent's moves", value=False, key="book_show_both")
        alerts = [x for x in report["alerts"]
                  if include_both or x["color"] == ("white" if user_color == chess.WHITE else "black")]
        if not alerts:
            st.caption("No significant evaluation drops found in the selected side's moves at this setting.")
        else:
            st.caption("Select an alert to jump to that move. Evaluation changes are estimates, not material counts.")
            counts = []
            for category_index, (name, _) in enumerate(BOOK_QUESTIONS):
                count = sum(1 for event in alerts if event["before_scan"][category_index]["detected"])
                if count:
                    counts.append((name, count))
            if counts:
                common = sorted(counts, key=lambda row: -row[1])[:3]
                st.caption("Patterns present before flagged moves (not proven causes): " +
                           "; ".join(f"{name} ({count})" for name, count in common))
            with st.container(height=205, border=True):
                for item in alerts:
                    label = f"{item['label']} · {item['quality']}"
                    if st.button(label, key=f"book_alert_{item['ply']}", use_container_width=True):
                        go_to_imported_move(item["ply"])
                        st.rerun()

        entire_narration = "\n\n".join(row["narration"] for row in report["records"])
        st.download_button(
            "Download full narrated game (.txt)", entire_narration,
            file_name="chess_book_game_narration.txt", mime="text/plain",
            use_container_width=True, key="download_book_review",
        )

    st.caption("The 12 categories are scanned with board rules, not 12 separate engines. "
               "A flagged pattern is a clue, not proof of a winning tactic. "
               "Stockfish judges missed opportunities by evaluation changes; deeper analysis can change a verdict.")


# ---------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------

if "active_opening" not in st.session_state:
    reset_game("London System")

if "pending_engine_move" not in st.session_state:
    st.session_state.pending_engine_move = computer_turn(
        board_from_state(), current_user_color()
    )


# ---------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------

st.sidebar.title("Training settings")

app_mode = st.sidebar.radio(
    "Mode", ["Play / game review", "Book puzzles"],
    key="chess_app_mode", horizontal=False,
)

selected_opening = st.sidebar.selectbox(
    "Opening",
    list(OPENINGS.keys()),
    index=list(OPENINGS.keys()).index(st.session_state.active_opening),
)

rating = st.sidebar.slider(
    "Opponent strength",
    min_value=800,
    max_value=2200,
    value=1200,
    step=50,
    help="1320+ uses Stockfish UCI_Elo. Lower ratings use an approximate weaker-move mode.",
)

flip_board = st.sidebar.toggle("Flip board", value=False)

detected_stockfish = auto_find_stockfish()

engine_path = st.sidebar.text_input(
    "Stockfish executable",
    value=detected_stockfish,
    placeholder=(r"C:\ChessTrainer\stockfish\stockfish.exe" if os.name == "nt" else "/usr/games/stockfish"),
)

if st.sidebar.button("New game", use_container_width=True):
    reset_game(selected_opening)
    st.rerun()

if selected_opening != st.session_state.active_opening:
    st.sidebar.info("Press New game to switch to this opening.")

with st.sidebar.expander("Import game / position"):
    import_side = st.selectbox(
        "I want to play as",
        ["White", "Black"],
        key="import_side"
    )

    st.markdown("##### PGN file")
    uploaded_pgn = st.file_uploader(
        "Upload PGN",
        type=["pgn"],
        key="pgn_upload"
    )

    st.markdown("##### Or paste PGN")
    pasted_pgn = st.text_area(
        "PGN",
        height=140,
        key="pasted_pgn",
        placeholder='[Event "..."]\n[White "..."]\n[Black "..."]\n\n1. e4 e5 ...'
    )

    pgn_text = ""
    if uploaded_pgn is not None:
        pgn_text = uploaded_pgn.getvalue().decode(
            "utf-8-sig",
            errors="replace"
        )
    elif pasted_pgn.strip():
        pgn_text = pasted_pgn.strip()

    if pgn_text:
        try:
            pgn_games = parse_pgn_games(pgn_text)
        except Exception as exc:
            pgn_games = []
            st.error(f"Could not read PGN: {exc}")

        if not pgn_games:
            st.warning("No games found in that PGN.")
        else:
            game_index = st.selectbox(
                f"Game ({len(pgn_games)} found)",
                range(len(pgn_games)),
                format_func=lambda i: pgn_game_label(pgn_games[i], i),
                key="pgn_game_index"
            )
            if st.button("Load PGN game", use_container_width=True, key="load_pgn"):
                load_pgn_game(pgn_games[game_index], import_side)
                st.rerun()

    st.markdown("##### Or paste FEN")
    fen_text = st.text_input(
        "FEN",
        key="import_fen",
        placeholder=chess.STARTING_FEN
    )
    if st.button("Load FEN position", use_container_width=True, key="load_fen"):
        if fen_text.strip():
            load_fen_position(fen_text, import_side)
        else:
            st.session_state.error = "Paste a FEN first."
        st.rerun()

st.sidebar.caption(
    "On Streamlit Cloud, packages.txt installs Stockfish automatically. "
    "On Windows, put your Stockfish .exe inside a folder named stockfish beside app.py."
)

# The book puzzle trainer is an independent mode: don't change the ongoing
# game / imported PGN state when the user practises a puzzle.
if app_mode == "Book puzzles":
    from book_puzzle_mode import render_book_puzzle_mode
    render_book_puzzle_mode(
        engine_path,
        chessboard_component,
        PIECE_IMAGES,
        board_position_dict,
        legal_move_map,
    )
    st.stop()


# ---------------------------------------------------------------------
# MAIN UI
# Stockfish replies when the board sends an "engine_move" trigger, a short
# moment after your move has finished animating.
# ---------------------------------------------------------------------

active = st.session_state.active_opening
if st.session_state.get("imported_mode", False):
    user_color = st.session_state.import_user_color
else:
    user_color = OPENINGS[active]["user_color"]

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.15rem; max-width: 1500px; }
        [data-testid="stMetric"] {
            background: rgba(128,128,128,.06);
            border: 1px solid rgba(128,128,128,.16);
            border-radius: 8px;
            padding: .6rem .8rem;
        }
        .move-row {
            display: grid;
            grid-template-columns: 2.5rem 1fr 1fr;
            gap: .45rem;
            padding: .34rem .5rem;
            border-radius: 4px;
            font-size: 1rem;
        }
        .move-row:nth-child(odd) { background: rgba(128,128,128,.08); }
        .move-no { opacity: .55; }
        .game-sub { opacity: .68; font-size: .92rem; margin-top:-.45rem; margin-bottom:.8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

board = board_from_state()
analysis = analyse_position(
    board,
    engine_path,
    show_threat=True
)
evaluation = analysis["evaluation"]
arrows = analysis["arrows"]
side_name = "White" if user_color == chess.WHITE else "Black"

if st.session_state.get("imported_mode", False):
    st.subheader(st.session_state.imported_label or "Imported game")
else:
    st.subheader(active)
st.markdown(
    f"<div class='game-sub'>You are {side_name} · Stockfish {rating}</div>",
    unsafe_allow_html=True,
)

if st.session_state.error:
    st.warning(st.session_state.error)
elif st.session_state.notice:
    st.success(st.session_state.notice)

if analysis["checkmate"]:
    winner = "Black" if board.turn == chess.WHITE else "White"
    st.error(f"Checkmate — {winner} wins.")
elif analysis["mate"] is not None:
    mate = analysis["mate"] if user_color == chess.WHITE else -analysis["mate"]
    if mate > 0:
        st.warning(f"Forced mate in {mate}")
    else:
        st.warning(f"Opponent has forced mate in {abs(mate)}")
else:
    game_result = result_message(board)
    if game_result:
        st.info(game_result)

left, right = st.columns([1.55, 0.8], gap="large")

with left:
    if st.session_state.get("coach_replay") and st.session_state.get("review_mode"):
        st.caption("Stockfish replay is active. Use Back / Next in the analysis panel. "
                   "Play from this position to explore the current branch.")
    default_orientation = "white" if user_color == chess.WHITE else "black"
    if flip_board:
        orientation = "black" if default_orientation == "white" else "white"
    else:
        orientation = default_orientation

    reviewing = st.session_state.get("review_mode", False)
    legal_moves, movable_squares = legal_move_map(
        board,
        user_color,
        analysis_mode=reviewing
    )
    coach_playback = bool(st.session_state.get("coach_replay")) and reviewing
    if coach_playback:
        # Playback is read-only. Exit replay or choose Play from this position.
        legal_moves, movable_squares = {}, []

    last_move = []
    if st.session_state.history:
        last = st.session_state.history[-1]
        last_move = [last[:2], last[2:4]]

    board_result = chessboard_component(
        key="main_chessboard",
        data={
            "position": board_position_dict(board),
            "evaluation": evaluation,
            "arrows": arrows,
            "piece_images": PIECE_IMAGES,
            "orientation": orientation,
            "legal_moves": legal_moves,
            "movable_squares": movable_squares,
            "user_turn": (
                (reviewing or board.turn == user_color)
                and not board.is_game_over()
                and not coach_playback
            ),
            "last_move": last_move,
            "pending_engine": (
                not reviewing
                and st.session_state.pending_engine_move
                and not board.is_game_over()
                and computer_turn(board, user_color)
            ),
            "move_number": len(st.session_state.history),
        },
        on_move_change=lambda: None,
        on_engine_move_change=lambda: None,
        width="stretch",
        height="content",
    )

    incoming_move = getattr(board_result, "move", None)
    if incoming_move and not coach_playback:
        from_sq = incoming_move.get("from")
        to_sq = incoming_move.get("to")
        if from_sq and to_sq:
            if reviewing:
                start_variation_move(from_sq, to_sq)
            else:
                try_user_move(chess.parse_square(from_sq), chess.parse_square(to_sq))
            st.rerun()

    engine_trigger = getattr(board_result, "engine_move", None)
    if engine_trigger and st.session_state.pending_engine_move and not reviewing:
        st.session_state.pending_engine_move = False
        board = board_from_state()

        if not board.is_game_over() and computer_turn(board, user_color):
            try:
                make_computer_move(engine_path, rating)
            except Exception as exc:
                st.session_state.error = str(exc)

        st.rerun()

with right:
    if reviewing and st.session_state.get("variation_mode", False):
        turn_text = "Analysing"
    elif reviewing:
        turn_text = "Reviewing"
    elif board.is_game_over():
        turn_text = "Game over"
    else:
        turn_text = "Your turn" if board.turn == user_color else "Opponent"

    m1, m2 = st.columns(2)
    m1.metric("Turn", turn_text)
    eval_label = ("M" if evaluation > 0 else "-M") if abs(evaluation) >= 99 else f"{evaluation:+.1f}"
    m2.metric("Eval", eval_label)

    if reviewing:
        total_moves = len(st.session_state.imported_moves)
        current = st.session_state.review_index

        st.caption(f"Move {current} of {total_moves}")

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button(
                "⏮",
                help="Beginning",
                use_container_width=True,
                disabled=current == 0
            ):
                go_to_imported_move(0)
                st.rerun()
        with b2:
            if st.button(
                "◀",
                help="Previous move",
                use_container_width=True,
                disabled=current == 0
            ):
                go_to_imported_move(current - 1)
                st.rerun()
        with b3:
            if st.button(
                "▶",
                help="Next move",
                use_container_width=True,
                disabled=current == total_moves
            ):
                go_to_imported_move(current + 1)
                st.rerun()
        with b4:
            if st.button(
                "⏭",
                help="Final position",
                use_container_width=True,
                disabled=current == total_moves
            ):
                go_to_imported_move(total_moves)
                st.rerun()

        in_variation = st.session_state.get("variation_mode", False)

        if in_variation:
            st.markdown("#### Analysis variation")
            st.caption(f"Branched from {variation_origin_label()}")

            variation_html = ""
            for number, white_move, black_move in move_history_rows(
                st.session_state.variation_moves,
                start_fen=variation_start_fen(),
            ):
                variation_html += (
                    "<div class='move-row'>"
                    f"<span class='move-no'>{number}.</span>"
                    f"<span>{white_move}</span>"
                    f"<span>{black_move}</span>"
                    "</div>"
                )
            st.markdown(variation_html, unsafe_allow_html=True)

            if st.button(
                "↩ Return to game",
                use_container_width=True,
                type="primary"
            ):
                return_to_game()
                st.rerun()

        if st.button(
            "Play from this position",
            use_container_width=True,
            type="secondary" if in_variation else "primary"
        ):
            play_from_review_position()
            st.rerun()

        with st.container(border=True):
            st.markdown("### Book-based game analysis")
            show_imported_book_review(engine_path, user_color)

        st.markdown("#### Moves")
        review_rows = imported_move_rows()

        # Keep the entire PGN move list inside one fixed-height review panel,
        # instead of allowing every move to extend the Streamlit page.
        with st.container(height=360, border=True):
            if not review_rows:
                st.caption("This game has no moves.")

            for row in review_rows:
                number_col, white_col, black_col = st.columns(
                    [0.18, 1, 1],
                    vertical_alignment="center",
                )
                number_col.markdown(f"**{row['number']}.**")

                if row["white"]:
                    white_active = current == row["white_index"]
                    if white_col.button(
                        row["white"],
                        key=f"review_white_{row['white_index']}",
                        use_container_width=True,
                        type="primary" if white_active else "secondary",
                    ):
                        go_to_imported_move(row["white_index"])
                        st.rerun()

                if row["black"]:
                    black_active = current == row["black_index"]
                    if black_col.button(
                        row["black"],
                        key=f"review_black_{row['black_index']}",
                        use_container_width=True,
                        type="primary" if black_active else "secondary",
                    ):
                        go_to_imported_move(row["black_index"])
                        st.rerun()

        # Chess.com-style evaluation history belongs directly under the
        # move list in the review panel. It follows the currently selected ply.
        if st.session_state.imported_moves:
            with st.spinner("Evaluating imported game…"):
                game_evals, game_labels = imported_game_evals(
                    st.session_state.base_fen,
                    tuple(st.session_state.imported_moves),
                    engine_path,
                )

            st.altair_chart(
                eval_graph(
                    game_evals,
                    game_labels,
                    st.session_state.review_index,
                    st.session_state.base_fen,
                ),
                use_container_width=True,
            )

    else:
        st.markdown("#### Moves")
        rows = move_history_rows(st.session_state.history)

        if rows:
            move_html = ""
            for number, white_move, black_move in rows:
                move_html += (
                    "<div class='move-row'>"
                    f"<span class='move-no'>{number}.</span>"
                    f"<span>{white_move}</span>"
                    f"<span>{black_move}</span>"
                    "</div>"
                )
            st.markdown(move_html, unsafe_allow_html=True)
        else:
            st.caption("No moves yet.")

    st.markdown("")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("↩ Take Back", use_container_width=True, disabled=reviewing):
            take_back()
            st.rerun()
    with c2:
        if st.button("Restart Game", use_container_width=True):
            reset_game(active)
            st.rerun()

    st.markdown("---")
    st.caption(
        "Drag a piece to move it, or click a piece and then its destination. "
        "The last move is highlighted. Stockfish plays from move 1 at the "
        "selected strength; the eval bar always uses full-strength Stockfish."
    )
