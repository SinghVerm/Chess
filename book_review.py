"""Book 1 Foundation: twelve ordered weakness prompts and PGN move narration.

Pattern flags are deterministic geometry/attack clues, not validated tactics.
Stockfish is used separately to judge whether the played move missed value.
"""

import chess
import chess.engine

from coach_layer import coach_from_lines

BOOK_QUESTIONS = [
    ("King safety", "Is the enemy king exposed or vulnerable?"),
    ("Unprotected pieces", "Which enemy pieces are undefended?"),
    ("Pieces on the same line", "Are enemy pieces aligned on a rank, file or diagonal?"),
    ("Opponent's last move", "What weakness did their last move create?"),
    ("Attackers vs defenders", "Can I outnumber the defenders of a target?"),
    ("Only one defender", "Is a target protected by just one piece?"),
    ("Overworked pieces", "Is one defender protecting multiple targets?"),
    ("Pinned pieces", "Is an enemy piece pinned?"),
    ("King focal points", "Are the squares around their king weak?"),
    ("Structural weaknesses", "Are there isolated/doubled pawns or weak squares?"),
    ("X-ray / hidden pressure", "What lies behind a piece on an openable line?"),
    ("Misplaced piece", "Is a piece trapped, inactive or short of squares?"),
]

PIECE = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
         chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}


def _name(piece, square):
    return f"{PIECE[piece.piece_type]} on {chess.square_name(square)}"


def _ray(a, b):
    """The unit direction if two squares share a rank/file/diagonal."""
    df = chess.square_file(b) - chess.square_file(a)
    dr = chess.square_rank(b) - chess.square_rank(a)
    if not (df == 0 or dr == 0 or abs(df) == abs(dr)) or (df == 0 and dr == 0):
        return None
    return ((df > 0) - (df < 0), (dr > 0) - (dr < 0))


def _between(board, a, b):
    step = _ray(a, b)
    if step is None:
        return None
    f, r = chess.square_file(a) + step[0], chess.square_rank(a) + step[1]
    result = []
    while (f, r) != (chess.square_file(b), chess.square_rank(b)):
        result.append(chess.square(f, r))
        f += step[0]
        r += step[1]
    return result


def scan_weaknesses(board, observer=None):
    """Return 12 entries in the book's original order.

    `observer` is the player looking for weaknesses in the opponent's position.
    Flags do NOT promise a winning move or even a tactical opportunity.
    """
    observer = board.turn if observer is None else observer
    victim = not observer
    own = [(s, p) for s, p in board.piece_map().items() if p.color == observer]
    enemy = [(s, p) for s, p in board.piece_map().items() if p.color == victim]
    found = [[] for _ in range(12)]

    def add(n, value):
        if value and value not in found[n] and len(found[n]) < 3:
            found[n].append(value)

    # 1. King safety: check candidates or specific pressure on the king's ring.
    king = board.king(victim)
    if king is not None:
        checking_moves = []
        if board.turn == observer:
            for move in board.legal_moves:
                if board.gives_check(move):
                    checking_moves.append(board.san(move))
                    if len(checking_moves) >= 2:
                        break
        if checking_moves:
            add(0, "Available checks: " + ", ".join(checking_moves))
        king_f, king_r = chess.square_file(king), chess.square_rank(king)
        pressed = []
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                f, r = king_f + df, king_r + dr
                if 0 <= f < 8 and 0 <= r < 8 and (df or dr):
                    square = chess.square(f, r)
                    a, d = len(board.attackers(observer, square)), len(board.attackers(victim, square))
                    if a >= 2 and a > d:
                        pressed.append(chess.square_name(square))
        if pressed:
            add(0, "Multiple attackers near the king: " + ", ".join(pressed[:3]))

    # 2. Loose/unprotected pieces: suppress normal undeveloped home-rank noise.
    for square, piece in enemy:
        if piece.piece_type == chess.KING:
            continue
        defenders = len(board.attackers(victim, square))
        attackers = len(board.attackers(observer, square))
        developed = chess.square_rank(square) not in ((0, 1) if victim == chess.WHITE else (6, 7))
        if defenders == 0 and (attackers or developed):
            add(1, f"{_name(piece, square)} is undefended" + (" and attacked" if attackers else ""))

    # 3. Alignments: a real enemy piece pair on a line, with a nearby line clue.
    important = [(s, p) for s, p in enemy if p.piece_type in (chess.KING, chess.QUEEN, chess.ROOK)]
    for j, (a, pa) in enumerate(important):
        for b, pb in important[j + 1:]:
            between = _between(board, a, b)
            if between is None or any(board.piece_at(s) for s in between):
                continue
            # Only flag if one square is currently attacked by the observer,
            # or an observer slider also aligns with the two targets.
            pressure = board.is_attacked_by(observer, a) or board.is_attacked_by(observer, b)
            slider = any(
                p.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN)
                and _ray(s, a) is not None and _ray(s, b) == _ray(s, a)
                for s, p in own
            )
            if pressure or slider:
                add(2, f"{_name(pa, a)} and {_name(pb, b)} share a line")

    # 4. Last-move drawbacks: defendership that actually disappeared.
    if board.move_stack and board.turn == observer:
        previous = board.copy(stack=True)
        last_move = previous.pop()
        for square, piece in enemy:
            old = previous.piece_at(square)
            if old is None or old.color != victim or old.piece_type != piece.piece_type:
                continue
            before = len(previous.attackers(victim, square))
            after = len(board.attackers(victim, square))
            if before > 0 and after == 0:
                add(3, f"The last move left {_name(piece, square)} undefended")
        moved = board.piece_at(last_move.to_square)
        if moved and moved.color == victim:
            if len(board.attackers(victim, last_move.to_square)) == 0 and board.is_attacked_by(observer, last_move.to_square):
                add(3, f"The last move placed {_name(moved, last_move.to_square)} on an attacked, undefended square")

    # 5. Attackers compared with defenders (pseudo-attacks are geometric,
    # including attacks by pinned pieces; engine still decides if they matter).
    for square, piece in enemy:
        if piece.piece_type == chess.KING:
            continue
        a, d = len(board.attackers(observer, square)), len(board.attackers(victim, square))
        if a > d and a:
            add(4, f"{_name(piece, square)}: {a} attacker(s) vs {d} defender(s)")

    # 6. One defender, and pressure or a valuable target.
    for square, piece in enemy:
        if piece.piece_type == chess.KING:
            continue
        defenders = len(board.attackers(victim, square))
        if defenders == 1 and (board.is_attacked_by(observer, square) or piece.piece_type in (chess.QUEEN, chess.ROOK)):
            defender = next(iter(board.attackers(victim, square)))
            add(5, f"{_name(piece, square)} relies on {chess.square_name(defender)}")

    # 7. Overworked: one defender is the sole defender of two attacked targets.
    burden = {}
    for square, piece in enemy:
        if piece.piece_type == chess.KING or not board.is_attacked_by(observer, square):
            continue
        defenders = list(board.attackers(victim, square))
        if len(defenders) == 1:
            burden.setdefault(defenders[0], []).append(square)
    for defender, targets in burden.items():
        if len(targets) >= 2:
            dp = board.piece_at(defender)
            if dp is not None:
                add(6, f"{_name(dp, defender)} alone defends {chess.square_name(targets[0])} and {chess.square_name(targets[1])}")

    # 8. Absolute pins to the king.
    for square, piece in enemy:
        if piece.piece_type != chess.KING and board.is_pinned(victim, square):
            add(7, f"{_name(piece, square)} is pinned to the king")

    # 9. Focal points, with an actual attacker.
    for file in (5, 6, 7):
        rank = 1 if victim == chess.WHITE else 6
        square = chess.square(file, rank)
        attackers = len(board.attackers(observer, square))
        if attackers:
            defenders = len(board.attackers(victim, square))
            if attackers >= defenders or board.king(victim) is not None and chess.square_file(board.king(victim)) >= 5:
                add(8, f"{chess.square_name(square)}: {attackers} attacker(s), {defenders} defender(s)")

    # 10. Structural pawn weaknesses; these are positional clues, not tactics.
    pawn_squares = list(board.pieces(chess.PAWN, victim))
    pawn_files = {chess.square_file(s) for s in pawn_squares}
    for file in range(8):
        group = [s for s in pawn_squares if chess.square_file(s) == file]
        if len(group) > 1:
            add(9, f"Doubled pawns on the {'abcdefgh'[file]}-file")
        if group and (file - 1 not in pawn_files) and (file + 1 not in pawn_files):
            add(9, f"Isolated pawn on {chess.square_name(group[0])}")

    # 11. X-ray: a slider points to a major target through exactly one piece.
    for square, piece in own:
        if piece.piece_type not in (chess.QUEEN, chess.ROOK, chess.BISHOP):
            continue
        for df, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            if piece.piece_type == chess.ROOK and df and dr:
                continue
            if piece.piece_type == chess.BISHOP and (df == 0 or dr == 0):
                continue
            f, r = chess.square_file(square), chess.square_rank(square)
            blocker = None
            while True:
                f += df
                r += dr
                if not (0 <= f < 8 and 0 <= r < 8):
                    break
                at = chess.square(f, r)
                obj = board.piece_at(at)
                if obj is None:
                    continue
                if blocker is None:
                    blocker = at
                else:
                    if obj.color == victim and obj.piece_type in (chess.KING, chess.QUEEN, chess.ROOK):
                        add(10, f"{_name(piece, square)} lines up with {_name(obj, at)} through {chess.square_name(blocker)}")
                    break

    # 12. Limited-mobility minor pieces, only after leaving the home rank.
    # Changing the side to move is solely for geometric mobility testing.
    future = board.copy(stack=False)
    future.turn = victim
    future.ep_square = None
    for square, piece in enemy:
        if piece.piece_type not in (chess.KNIGHT, chess.BISHOP, chess.QUEEN):
            continue
        if chess.square_rank(square) == (0 if victim == chess.WHITE else 7):
            continue
        mobility = sum(1 for move in future.legal_moves if move.from_square == square)
        if mobility <= 2:
            add(11, f"{_name(piece, square)} has only {mobility} legal move(s)")

    return [
        {"number": i + 1, "name": name, "question": question,
         "detected": bool(found[i]), "examples": found[i]}
        for i, (name, question) in enumerate(BOOK_QUESTIONS)
    ]


def _engine_position(engine, board, seconds):
    if board.is_checkmate():
        value = -10000 if board.turn == chess.WHITE else 10000
        return {"cp": value, "mate": -1 if board.turn == chess.WHITE else 1, "best": None, "pv": []}
    if board.is_game_over():
        return {"cp": 0, "mate": None, "best": None, "pv": []}
    if engine is None:
        return None
    try:
        info = engine.analyse(board, chess.engine.Limit(time=seconds, depth=18))
        score = info["score"].white()
        pv = [m.uci() for m in info.get("pv", [])[:12]]
        return {"cp": score.score(mate_score=10000), "mate": score.mate(),
                "best": pv[0] if pv else None, "pv": pv}
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, OSError):
        return None


def _san_line(board, ucis):
    branch = board.copy(stack=False)
    result = []
    for uci in ucis:
        try:
            move = chess.Move.from_uci(uci)
            if move not in branch.legal_moves:
                break
            prefix = f"{branch.fullmove_number}{'.' if branch.turn == chess.WHITE else '...'}"
            result.append(prefix + " " + branch.san(move))
            branch.push(move)
        except (ValueError, AssertionError):
            break
    return " ".join(result)


def _classify(before, after, mover, played, best):
    if before is None or after is None:
        return "Not scored", None, None
    pre = before["cp"] * (1 if mover == chess.WHITE else -1)
    post = after["cp"] * (1 if mover == chess.WHITE else -1)
    if before["mate"] is not None and before["mate"] * (1 if mover == chess.WHITE else -1) > 0 and not (
        after["mate"] is not None and after["mate"] * (1 if mover == chess.WHITE else -1) > 0
    ):
        return "Missed forced mate", max(0, pre - post), "mate"
    if after["mate"] is not None and after["mate"] * (1 if mover == chess.WHITE else -1) < 0 and not (
        before["mate"] is not None and before["mate"] * (1 if mover == chess.WHITE else -1) < 0
    ):
        return "Allowed forced mate", max(0, pre - post), "mate"
    loss = max(0, pre - post)
    if played == best:
        return "Engine choice", loss, None
    if loss >= 150:
        return "Blunder", loss, None
    if loss >= 80:
        return "Mistake", loss, None
    if loss >= 35:
        return "Inaccuracy", loss, None
    return "Reasonable", loss, None


def _short_san_line(board, moves, limit=6):
    """SAN from the correct branch; variations are evidence, not prose."""
    return _san_line(board, (moves or [])[:limit])


def _describe_move(board, move):
    """A short, board-verified description, without claiming the move is good."""
    piece = board.piece_at(move.from_square)
    if piece is None:
        return "makes a move"
    destination = chess.square_name(move.to_square)
    if board.is_castling(move):
        return "castles to protect the king"
    if board.is_capture(move):
        taken = board.piece_at(move.to_square)
        if board.is_en_passant(move):
            taken = chess.Piece(chess.PAWN, not board.turn)
        if taken:
            return f"captures the {PIECE[taken.piece_type]} on {destination}"
    home_minor = {
        chess.WHITE: {chess.B1, chess.G1, chess.C1, chess.F1},
        chess.BLACK: {chess.B8, chess.G8, chess.C8, chess.F8},
    }
    if piece.piece_type in (chess.KNIGHT, chess.BISHOP) and move.from_square in home_minor[board.turn]:
        return f"develops the {PIECE[piece.piece_type]} to {destination}"
    if board.gives_check(move):
        return "gives check"
    return f"moves the {PIECE[piece.piece_type]} to {destination}"

def _pv_events(start, pv, previous_capture=None, limit=10):
    """Validate the actual PV and mark routine recaptures explicitly."""
    branch = start.copy(stack=False)
    events = []
    last_capture = previous_capture
    for uci in (pv or [])[:limit]:
        try:
            move = chess.Move.from_uci(uci)
            if move not in branch.legal_moves:
                break
        except ValueError:
            break
        captured = branch.piece_at(move.to_square)
        if branch.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not branch.turn)
        capturing = captured is not None
        san = branch.san(move)
        color = branch.turn
        mover = branch.piece_at(move.from_square)
        recapture = capturing and last_capture == move.to_square
        prefix = f"{branch.fullmove_number}{'.' if color == chess.WHITE else '...'}"
        branch.push(move)
        direct_targets = []
        if mover is not None:
            for square in branch.attacks(move.to_square):
                target = branch.piece_at(square)
                if target is not None and target.color != color and target.piece_type in (
                    chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN
                ):
                    direct_targets.append((square, target))
        events.append({
            "san": san, "label": f"{prefix} {san}", "color": color,
            "captured": captured, "recapture": recapture, "square": move.to_square,
            "check": branch.is_check(), "checkmate": branch.is_checkmate(),
            "targets": direct_targets,
        })
        last_capture = move.to_square if capturing else None
    return events


def _recaptured(events, n):
    return (n + 1 < len(events) and events[n + 1]["recapture"]
            and events[n + 1]["square"] == events[n]["square"])


def _explain_reply(board, move, after):
    """Readable grounded consequence; avoid calling normal exchanges blunders.

    Stockfish scores the position. Neither the score nor one PV proves a
    strategic cause, so we explicitly say when the reason isn't established.
    """
    result = {"reply": None, "reason": "", "lesson": "", "line": "", "kind": "unclear"}
    if not after or not after.get("pv"):
        result["reason"] = "The engine did not provide a continuation that explains the problem."
        return result

    position = board.copy(stack=False)
    position.push(move)
    them = position.turn
    opponent = "White" if them == chess.WHITE else "Black"
    events = _pv_events(position, after["pv"], move.to_square if board.is_capture(move) else None)
    result["line"] = _short_san_line(position, after["pv"], limit=8)
    if not events:
        result["reason"] = "The engine continuation could not be verified as legal."
        return result

    first = events[0]
    result["reply"] = first["label"]
    # Mate is checked against both the returned evaluation and continuation.
    mate = after.get("mate")
    opponent_mates = mate is not None and (mate > 0) == (them == chess.WHITE)
    if first["checkmate"]:
        result.update(kind="mate", reason=f"{opponent} can checkmate immediately with {first['san']}.",
                      lesson="King safety: what checks can my opponent give after this move?")
        return result
    if opponent_mates:
        result.update(kind="mate", reason=(f"{opponent} has a forced mating attack according to Stockfish, "
                         f"beginning with {first['label']}. The checks, not the pawn count, are the priority."),
                      lesson="King safety: what forcing checks have I allowed?")
        return result

    # Real captures can be instructive, but never say a piece was 'won' when
    # a recapture is visible in the very next move of the supplied line.
    for i, event in enumerate(events[:8]):
        if event["color"] != them or event["captured"] is None or event["recapture"]:
            continue
        if event["captured"].piece_type < chess.KNIGHT:
            continue
        captured_name = PIECE[event["captured"].piece_type]
        location = chess.square_name(event["square"])
        if _recaptured(events, i):
            continue
        lead = (f"{opponent}'s immediate reply {first['label']} " if i == 0
                else f"After {first['label']}, the line also reaches {event['label']}, which ")
        if i == 0:
            fact = f"takes your {captured_name} on {location}"
            reason = lead + fact + "."
        else:
            reason = lead + f"captures your {captured_name} on {location}."
        result.update(kind="tactic", reason=reason,
                      lesson="Unprotected pieces: what could my opponent capture after my move?")
        return result

    # A reply can create a visible double attack even without an immediate capture.
    if first["targets"]:
        priority = sorted(first["targets"], key=lambda x: x[1].piece_type, reverse=True)
        if len(priority) >= 2:
            one, two = priority[:2]
            result.update(kind="threat", reason=(
                f"{opponent} can answer with {first['label']}, attacking both your "
                f"{PIECE[one[1].piece_type]} on {chess.square_name(one[0])} and "
                f"{PIECE[two[1].piece_type]} on {chess.square_name(two[0])}."),
                lesson="Unprotected pieces: can my opponent attack two of my pieces at once?")
            return result

    # An ordinary recapture is important to see, but it does not by itself
    # explain a one-pawn engine evaluation swing.
    if first["recapture"]:
        rest = next((e for e in events[1:8]
                     if e["color"] == them and e["captured"] is not None
                     and e["captured"].piece_type >= chess.KNIGHT), None)
        reason = (f"{opponent} replies {first['label']} and recaptures. "
                  "That's a normal trade, so you haven't simply hung a pawn.")
        if rest:
            idx = events.index(rest)
            piece_name = PIECE[rest["captured"].piece_type]
            target_sq = chess.square_name(rest["square"])
            if _recaptured(events, idx):
                reason += (f" Later {rest['label']} takes your {piece_name} on {target_sq}, "
                           f"but {events[idx + 1]['label']} recaptures. That's another exchange.")
            else:
                reason += f" The next important moment is {rest['san']}, taking your {piece_name} on {target_sq}."
        reason += (" The engine score has dropped, but these trades alone don't explain why. "
                   "The useful comparison is how the pieces and pawns stand afterward.")
        result.update(kind="exchange", reason=reason,
                      lesson="Attackers versus defenders: after all recaptures, who benefits from the resulting position?")
        return result

    if first["check"]:
        result.update(kind="check", reason=(
            f"{opponent} can answer with {first['label']}, giving check. "
            "This forces you to respond, though the short line alone may not show a material loss."),
            lesson="King safety: what forcing checks can my opponent play next?")
        return result

    # If the PV doesn't explain the numerical score, say so clearly.
    result.update(kind="unclear", reason=(
        f"{opponent}'s preferred reply is {first['label']}. The engine prefers "
        "the resulting position, but its short line does not show a clear forced "
        "material win or a single tactical refutation. A deeper review may be needed."))
    return result


def _better_move_explanation(board, played, best_uci, best_san):
    if not best_uci or not best_san:
        return ""
    try:
        alternative = chess.Move.from_uci(best_uci)
        if alternative not in board.legal_moves:
            return ""
    except ValueError:
        return ""

    piece = board.piece_at(alternative.from_square)
    reason = _describe_move(board, alternative)
    # Only make a comparative claim when its underlying fact is on the board.
    if (board.is_capture(played) and board.piece_at(played.from_square)
            and board.piece_at(played.from_square).piece_type == chess.PAWN
            and piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP)
            and alternative.from_square in (
                chess.B1, chess.G1, chess.C1, chess.F1,
                chess.B8, chess.G8, chess.C8, chess.F8
            )):
        return f"{best_san} {reason} while keeping the central pawns in place rather than exchanging them immediately."
    if board.is_castling(alternative):
        return f"{best_san} {reason}, addressing king safety before looking for tactics."
    # Describe a newly established direct attack without promising it wins material.
    next_board = board.copy(stack=False)
    next_board.push(alternative)
    victim = next_board.piece_at(alternative.to_square)
    if victim:
        attacked = [
            (sq, next_board.piece_at(sq)) for sq in next_board.attacks(alternative.to_square)
            if next_board.piece_at(sq) is not None
            and next_board.piece_at(sq).color != piece.color
            and next_board.piece_at(sq).piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
        ]
        if attacked:
            sq, target = sorted(attacked, key=lambda x: x[1].piece_type, reverse=True)[0]
            return f"{best_san} {reason} and attacks the {PIECE[target.piece_type]} on {chess.square_name(sq)}."
    return f"{best_san} {reason}. Stockfish prefers this at the selected depth."


def narrate(move_record):
    """Intermediate-level coach: idea, verified consequence, better choice."""
    if move_record.get("start"):
        return "Before moving, look for a weakness. Then consider checks, captures and threats."

    mover = move_record["mover"]
    label = move_record["label"]
    quality = move_record["quality"]
    event = quality in ("Blunder", "Mistake", "Inaccuracy", "Missed forced mate", "Allowed forced mate")
    description = move_record.get("played_description") or "makes a move"
    for verb, form in (("captures ", "capturing "), ("develops ", "developing "),
                       ("moves ", "moving "), ("castles ", "castling "),
                       ("gives ", "giving ")):
        if description.startswith(verb):
            description = form + description[len(verb):]
            break
    sections = {}

    if quality == "Not scored":
        sections["What happened"] = f"{mover} played {label}, {description}."
        sections["What to check"] = ("Look at the opponent's checks and captures, then ask whether "
                                     "your move has left a piece or square vulnerable. "
                                     "Run the engine review for a verdict.")
    elif event:
        intro = (f"{label} missed a chance to force mate." if quality == "Missed forced mate"
                 else f"{label} allowed a forced mating attack." if quality == "Allowed forced mate"
                 else f"{label} was a {quality.lower()}.")
        sections["What happened"] = intro
        coach = move_record.get("coach")
        if coach:
            sections["What you overlooked"] = coach["why"]
            if move_record.get("best_san"):
                sections["What was better"] = coach["better"]
            sections["Book question"] = coach["lesson"]
            if coach["confidence"] == "limited":
                sections["Analysis limit"] = ("This engine line is evidence, not proof of the exact cause. "
                                               "Use the replay or deeper analysis to investigate.")
        else:
            sections["What you overlooked"] = ("No verified engine continuation is available. "
                                                 "Check the opponent's next checks, captures and threats.")
            if move_record.get("best_san"):
                sections["What was better"] = move_record.get("best_reason") or move_record["best_san"]
            sections["Book question"] = "What can my opponent do immediately after this move?"
    else:
        sections["What happened"] = f"{mover} played {label}, {description}."
        sections["Coach's view"] = ("Stockfish likes this move at the selected depth." if quality == "Engine choice"
                                    else "The review found no major drawback at this depth.")
        if move_record.get("after_check"):
            sections["Coach's view"] += " It also puts the opponent in check."

    move_record["sections"] = sections
    return " ".join(sections.values())

def _record(board, move, before, after):
    observer = board.turn
    scan = scan_weaknesses(board, observer)
    label = f"{board.fullmove_number}{'.' if observer == chess.WHITE else '...'} {board.san(move)}"
    best_uci = before.get("best") if before else None
    best_san = None
    if best_uci:
        try:
            cand = chess.Move.from_uci(best_uci)
            if cand in board.legal_moves:
                best_san = board.san(cand)
        except ValueError:
            pass
    quality, loss_cp, special = _classify(before, after, observer, move.uci(), best_uci)
    follow = board.copy(stack=False)
    follow.push(move)
    reply = _explain_reply(board, move, after)
    coach = coach_from_lines(board, move, before, after) if before and after else None
    result = {
        "label": label, "mover": "White" if observer == chess.WHITE else "Black",
        "color": "white" if observer == chess.WHITE else "black", "played_san": board.san(move),
        "played_uci": move.uci(), "quality": quality, "loss_cp": loss_cp,
        "mate_event": special, "best_san": best_san,
        "best_line": _short_san_line(board, before.get("pv", [])) if before else "",
        "played_line": reply["line"],
        "reply_san": reply["reply"],
        "reply_kind": reply["kind"],
        "coach": coach,
        "played_steps": coach["played_steps"] if coach else [],
        "better_steps": coach["better_steps"] if coach else [],
        "played_description": _describe_move(board, move),
        "best_reason": _better_move_explanation(board, move, best_uci, best_san),
        "reply_reason": reply["reason"],
        "reply_lesson": reply["lesson"],
        "before_scan": scan, "after_scan": scan_weaknesses(follow, not observer),
        "capture": board.is_capture(move), "after_check": follow.is_check(),
        "before_eval": before["cp"] / 100 if before and before.get("cp") is not None else None,
        "after_eval": after["cp"] / 100 if after and after.get("cp") is not None else None,
    }
    result["narration"] = narrate(result)
    return result


def review_pgn(base_fen, uci_moves, engine_path, seconds=0.18):
    """One engine pass per position, with per-move twelve-weakness narratives."""
    board = chess.Board(base_fen)
    moves = list(uci_moves)
    engine = None
    engine_error = None
    if engine_path:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        except (OSError, chess.engine.EngineError, chess.engine.EngineTerminatedError) as exc:
            engine_error = str(exc)
    else:
        engine_error = "Stockfish executable not configured."
    try:
        positions = [_engine_position(engine, board, seconds)]
        for uci in moves:
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal imported move: {uci}")
            board.push(move)
            positions.append(_engine_position(engine, board, seconds))
        board = chess.Board(base_fen)
        records = []
        for index, uci in enumerate(moves):
            move = chess.Move.from_uci(uci)
            before, after = positions[index], positions[index + 1]
            initial_quality, _, _ = _classify(before, after, board.turn, uci, before.get("best") if before else None)
            # Spend extra time on critical errors. A refutation line from only
            # 0.2 seconds is particularly likely to miss the key continuation.
            if engine and initial_quality in ("Blunder", "Mistake", "Missed forced mate", "Allowed forced mate"):
                deeper = max(0.5, seconds * 3)
                refined_before = _engine_position(engine, board, deeper)
                next_board = board.copy(stack=False)
                next_board.push(move)
                refined_after = _engine_position(engine, next_board, deeper)
                if refined_before and refined_after:
                    before, after = refined_before, refined_after
            record = _record(board, move, before, after)
            record["ply"] = index + 1
            records.append(record)
            board.push(move)
        alerts = [x for x in records if x["quality"] in ("Inaccuracy", "Mistake", "Blunder", "Missed forced mate", "Allowed forced mate")]
        return {"records": records, "alerts": alerts, "engine_error": engine_error,
                "scored": sum(1 for r in records if r["loss_cp"] is not None),
                "seconds": seconds}
    finally:
        if engine:
            try:
                engine.quit()
            except Exception:
                pass


def quick_move_review(base_fen, uci_moves, index):
    """Immediate text narration and scan without waiting for a full engine review."""
    board = chess.Board(base_fen)
    if index <= 0:
        row = {"start": True, "before_scan": scan_weaknesses(board)}
        row["narration"] = narrate(row)
        return row
    for uci in uci_moves[:index - 1]:
        board.push(chess.Move.from_uci(uci))
    move = chess.Move.from_uci(uci_moves[index - 1])
    return _record(board, move, None, None)


def deepen_move(base_fen, uci_moves, ply, engine_path, seconds=2.0):
    """Re-check one chosen imported move and both branches at higher effort.

    This is intentionally on-demand, not a huge slowdown for the full PGN.
    """
    if not engine_path:
        raise ValueError("Configure a Stockfish executable first.")
    if ply < 1 or ply > len(uci_moves):
        raise ValueError("Choose a played move to analyse.")
    board = chess.Board(base_fen)
    for uci in uci_moves[:ply - 1]:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"Illegal imported move: {uci}")
        board.push(move)
    played = chess.Move.from_uci(uci_moves[ply - 1])
    if played not in board.legal_moves:
        raise ValueError("The selected PGN move is not legal.")
    next_board = board.copy(stack=False)
    next_board.push(played)
    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    try:
        before = _engine_position(engine, board, seconds)
        after = _engine_position(engine, next_board, seconds)
        if not before or not after:
            raise RuntimeError("Stockfish did not provide a complete analysis.")
        row = _record(board, played, before, after)
        row["ply"] = ply
        row["deepened"] = True
        return row
    finally:
        engine.quit()
