"""Evidence-driven Stockfish coach and legal, step-by-step replay data.

All specific claims here are checked against python-chess positions; a
principal variation is an engine sample, not a proof of a unique cause.
"""

import chess

NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
         chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}
CENTRE = {chess.D4, chess.E4, chess.D5, chess.E5}
HOME_MINOR = {chess.B1, chess.G1, chess.C1, chess.F1,
              chess.B8, chess.G8, chess.C8, chess.F8}


def piece_at(board, square):
    piece = board.piece_at(square)
    return f"{NAMES[piece.piece_type]} on {chess.square_name(square)}" if piece else "piece"


def _label(board, move):
    return f"{board.fullmove_number}{'.' if board.turn else '...'} {board.san(move)}"


def legal_line(start, sequence, max_plies=13):
    """Discard non-legal or truncated engine PV moves, preserving only legal play."""
    board = start.copy(stack=False)
    out = []
    for uci in (sequence or [])[:max_plies]:
        try:
            move = chess.Move.from_uci(uci)
        except (TypeError, ValueError):
            break
        if move not in board.legal_moves:
            break
        out.append(uci)
        board.push(move)
    return out


def _attacked_minors(board, color):
    """Already-attacked pieces; this is NOT a claim that they are hanging."""
    attacked = []
    for sq, p in board.piece_map().items():
        if p.color != color or p.piece_type not in (chess.BISHOP, chess.KNIGHT, chess.QUEEN):
            continue
        if board.is_attacked_by(not color, sq):
            developed = sq not in HOME_MINOR
            attacked.append((0 if developed else 1, 0 if p.piece_type == chess.BISHOP else 1, sq))
    return [piece_at(board, s) for _, _, s in sorted(attacked)][:3]


def _new_targets(before, move):
    """Specific enemy pieces directly attacked from the moved piece's destination."""
    piece = before.piece_at(move.from_square)
    if not piece:
        return []
    after = before.copy(stack=False)
    after.push(move)
    targets = []
    for square in after.attacks(move.to_square):
        target = after.piece_at(square)
        if target and target.color != piece.color and target.piece_type in (
            chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN
        ):
            targets.append((target.piece_type, piece_at(after, square)))
    return [x[1] for x in sorted(targets, key=lambda x: -x[0])]


def _plain_capture(before, move):
    if not before.is_capture(move):
        return None
    if before.is_en_passant(move):
        return "pawn"
    taken = before.piece_at(move.to_square)
    return NAMES[taken.piece_type] if taken else None


def line_steps(start, sequence, previously_captured_square=None):
    """Return replayable, annotated legal plies from one chosen branch."""
    moves = legal_line(start, sequence)
    board = start.copy(stack=False)
    result = []
    last_capture = previously_captured_square
    for n, uci in enumerate(moves):
        m = chess.Move.from_uci(uci)
        mover = "White" if board.turn else "Black"
        san = board.san(m)
        label = _label(board, m)
        piece = board.piece_at(m.from_square)
        capture = _plain_capture(board, m)
        check = board.gives_check(m)
        recapture = capture and last_capture == m.to_square
        targets = _new_targets(board, m)
        next_recapture = False
        recapture_san = None
        if capture and n + 1 < len(moves):
            next_move = chess.Move.from_uci(moves[n + 1])
            follow = board.copy(stack=False)
            follow.push(m)
            if next_move in follow.legal_moves and follow.is_capture(next_move) and next_move.to_square == m.to_square:
                next_recapture = True
                recapture_san = follow.san(next_move)

        if check:
            king = board.king(not board.turn)
            note = f"{mover} gives check to the king on {chess.square_name(king)}; the king must be made safe."
            if capture:
                note += f" It also captures the {capture} on {chess.square_name(m.to_square)}."
        elif capture:
            if recapture:
                note = f"{mover} recaptures on {chess.square_name(m.to_square)}, continuing the exchange."
            elif next_recapture:
                note = (f"{mover} captures the {capture} on {chess.square_name(m.to_square)}, "
                        f"but {recapture_san} immediately recaptures. That is an exchange, not a free piece.")
            else:
                note = f"{mover} captures the {capture} on {chess.square_name(m.to_square)}."
                note += " The displayed line shows no immediate recapture." if n + 1 < len(moves) else ""
        elif board.is_castling(m):
            note = f"{mover} castles, improving king safety."
        elif piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP) and m.from_square in HOME_MINOR:
            note = f"{mover} develops the {NAMES[piece.piece_type]} to {chess.square_name(m.to_square)}."
        else:
            note = f"{mover} plays {san}."
        if not check and piece and piece.piece_type == chess.KNIGHT and m.to_square in CENTRE:
            note += f" The knight occupies the central square {chess.square_name(m.to_square)}."
        if targets:
            if check:
                note += " At the same time, it attacks " + " and ".join(targets[:2]) + "."
            else:
                note += " From there it attacks " + " and ".join(targets[:2]) + "."
        board.push(m)
        if board.is_checkmate():
            note += " This is checkmate."
        result.append({"uci": uci, "san": san, "label": label, "note": note,
                       "check": check, "targets": targets, "fen": board.fen()})
        last_capture = m.to_square if capture else None
    return result


def coach_from_lines(before_board, played, before_eval, after_eval):
    """Build two verifiable continuations, and reason from their key moments.

    Statements are explicitly conservative: existing attacks don't guarantee
    material loss; a capture with a recapture is not counted as a free piece.
    """
    move_uci = played.uci()
    after_board = before_board.copy(stack=False)
    after_board.push(played)
    best_pv = legal_line(before_board, before_eval.get("pv") if before_eval else [])
    reply_pv = legal_line(after_board, after_eval.get("pv") if after_eval else [], max_plies=12)
    played_line = line_steps(before_board, [move_uci] + reply_pv)
    best_line = line_steps(before_board, best_pv)
    opponent = "White" if after_board.turn else "Black"
    mover = "White" if before_board.turn else "Black"
    before_pressure = set(_attacked_minors(before_board, before_board.turn))
    # Only mention threats that genuinely persist after the move played.
    initial_pressure = [x for x in _attacked_minors(after_board, before_board.turn)
                        if x in before_pressure]
    first = chess.Move.from_uci(reply_pv[0]) if reply_pv else None
    first_label = _label(after_board, first) if first else None
    first_check = after_board.gives_check(first) if first else False
    first_capture = _plain_capture(after_board, first) if first else None
    first_recapture = bool(first_capture and before_board.is_capture(played)
                           and first.to_square == played.to_square) if first else False
    centralized_knight = bool(first and after_board.piece_at(first.from_square)
                              and after_board.piece_at(first.from_square).piece_type == chess.KNIGHT
                              and first.to_square in CENTRE)
    first_targets = _new_targets(after_board, first) if first else []
    first_reply = first_label or "no legal continuation available"

    if not first:
        why = "The engine did not return a follow-up line that can be replayed."
        lesson = "Before moving, what checks, captures and threats does my opponent have?"
        confidence = "limited"
    elif after_eval and after_eval.get("mate") is not None and (
        (after_eval["mate"] > 0) == (after_board.turn == chess.WHITE)
    ):
        why = (f"After your move, {opponent} has a forced mating attack according to Stockfish, "
               f"starting with {first_reply}. Check the replies on the board to see how the king is restricted.")
        lesson = "King safety (1): What checks and mating threats can my opponent play?"
        confidence = "engine-mate"
    elif first_check:
        king = after_board.king(before_board.turn)
        why = (f"{opponent} can immediately play {first_reply}, checking your king on "
               f"{chess.square_name(king)}. You must respond to the check first.")
        if initial_pressure:
            why += (" Meanwhile, " + " and ".join("your " + s for s in initial_pressure[:2]) +
                    " were already under attack. The check makes those threats harder to deal with calmly.")
        double_attack_check = next((step for step in played_line[2:10]
                                    if step.get("check") and step.get("targets")), None)
        follow_important = next((step for step in played_line[2:8]
                                 if step.get("check")), None)
        if double_attack_check:
            why += (f" Later {double_attack_check['label']} checks again while also attacking "
                    + " and ".join("your " + t for t in double_attack_check["targets"][:2]) + ".")
        elif follow_important:
            why += f" The continuation also includes {follow_important['label']}, another forcing check."
        lesson = "King safety (1): Before my move, what checks can my opponent play?"
        confidence = "verified-check"
    elif first_recapture and centralized_knight:
        target_text = (" and immediately attacks " + " and ".join("your " + s for s in first_targets[:2])) if first_targets else ""
        why = (f"After the exchange, {opponent} answers {first_reply}. The knight lands on "
               f"the central square {chess.square_name(first.to_square)}{target_text}. "
               "This is a normal recapture, but it improves the knight's activity; don't mistake it for a free pawn win.")
        lesson = "Opponent's last move (4): After an exchange, where will their pieces land and what will they attack?"
        confidence = "verified-positional"
    elif first_check is False and centralized_knight and first_targets:
        why = (f"{opponent} can play {first_reply}, centralising the knight and attacking "
               + " and ".join("your " + s for s in first_targets[:2]) + ".")
        lesson = "Misplaced pieces (12): Which enemy piece becomes more active after the move?"
        confidence = "verified-pressure"
    elif first_capture:
        first_step = played_line[1] if len(played_line) > 1 else None
        why = f"{opponent} replies {first_reply}, capturing your {first_capture} on {chess.square_name(first.to_square)}."
        if first_step and "immediately recaptures" in first_step["note"]:
            why += " The line includes an immediate recapture, so this is an exchange rather than a free loss."
            lesson = "Attackers versus defenders (5): After the complete exchange, who benefits?"
        else:
            why += " Step through the continuation to check whether a recapture is possible."
            lesson = "Unprotected pieces (2): What captures can my opponent make after my move?"
        confidence = "verified-capture"
    elif len(first_targets) >= 2:
        why = (f"{opponent} replies {first_reply}, attacking both "
               + " and ".join("your " + s for s in first_targets[:2]) + ".")
        lesson = "Overworked pieces (7): Can the opponent create two threats at once?"
        confidence = "verified-double-threat"
    else:
        why = (f"Stockfish prefers {first_reply} after your move. The displayed continuation doesn't "
               "yet establish a clear tactical refutation, so don't assume a material loss. "
               "Compare the resulting piece activity, king safety and pawn structure with the better line.")
        lesson = "Opponent's last move (4): What new possibilities does it create for them?"
        confidence = "limited"

    if best_line:
        best_move = chess.Move.from_uci(best_line[0]["uci"])
        moving = before_board.piece_at(best_move.from_square)
        targets = _new_targets(before_board, best_move)
        dest = chess.square_name(best_move.to_square)
        if before_board.is_castling(best_move):
            better = f"{best_line[0]['label']} protects your king by castling."
        elif moving and moving.piece_type in (chess.KNIGHT, chess.BISHOP) and best_move.from_square in HOME_MINOR:
            better = f"{best_line[0]['label']} develops your {NAMES[moving.piece_type]} to {dest}."
        elif before_board.is_capture(best_move):
            better = f"{best_line[0]['label']} captures on {dest}."
        else:
            better = f"{best_line[0]['label']} is Stockfish's preferred alternative."
        if targets:
            better += " It also attacks " + " and ".join("the opponent's " + x for x in targets[:2]) + "."
        elif moving and moving.piece_type == chess.KNIGHT and best_move.to_square in CENTRE:
            better += " It puts your knight in the centre."
        if len(best_line) >= 2:
            better += f" In the engine's sample continuation, {best_line[1]['label']} follows."
    else:
        better = "No legal best-move line was returned by Stockfish."

    return {
        "why": why, "better": better, "lesson": lesson, "confidence": confidence,
        "played_steps": played_line, "better_steps": best_line,
    }
