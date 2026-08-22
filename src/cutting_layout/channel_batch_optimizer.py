from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product

from ortools.sat.python import cp_model

from .channel_batch import ChannelBatch, ChannelBatchPlan, validate_batch_plan


@dataclass
class _ModelVariables:
    model: cp_model.CpModel
    multiplicity: list[cp_model.IntVar]
    stock: list[cp_model.IntVar]
    stock_total: list[cp_model.IntVar]
    per_bar: dict[tuple[int, int], cp_model.IntVar]
    cuts: cp_model.LinearExpr
    total_stock: cp_model.LinearExpr
    type_groups: cp_model.LinearExpr


def _build_model(
    demand: Counter[int],
    *,
    batch_count: int,
    kerf: int,
    max_stack: int,
    min_bars: int,
    max_bars: int,
    stock_lengths: tuple[int, ...],
) -> _ModelVariables:
    model = cp_model.CpModel()
    lengths = sorted(demand, reverse=True)
    multiplicity: list[cp_model.IntVar] = []
    stock: list[cp_model.IntVar] = []
    stock_total: list[cp_model.IntVar] = []
    per_bar: dict[tuple[int, int], cp_model.IntVar] = {}
    produced: dict[tuple[int, int], cp_model.IntVar] = {}
    present: dict[tuple[int, int], cp_model.BoolVar] = {}

    for batch in range(batch_count):
        batch_multiplicity = model.new_int_var(1, max_stack, f"m_{batch}")
        batch_stock = model.new_int_var_from_domain(
            cp_model.Domain.FromValues(stock_lengths), f"stock_{batch}"
        )
        batch_stock_total = model.new_int_var(
            min(stock_lengths), max(stock_lengths) * max_stack, f"stock_total_{batch}"
        )
        model.add_multiplication_equality(
            batch_stock_total,
            [batch_multiplicity, batch_stock],
        )
        multiplicity.append(batch_multiplicity)
        stock.append(batch_stock)
        stock_total.append(batch_stock_total)

        batch_piece_vars = []
        for index, length in enumerate(lengths):
            maximum = min(demand[length], max(stock_lengths) // (length + kerf))
            quantity = model.new_int_var(0, maximum, f"q_{index}_{batch}")
            output = model.new_int_var(0, demand[length], f"p_{index}_{batch}")
            exists = model.new_bool_var(f"y_{index}_{batch}")
            model.add_multiplication_equality(
                output,
                [batch_multiplicity, quantity],
            )
            model.add(quantity >= exists)
            model.add(quantity <= maximum * exists)
            per_bar[index, batch] = quantity
            produced[index, batch] = output
            present[index, batch] = exists
            batch_piece_vars.append(quantity)

        model.add(sum(batch_piece_vars) >= 1)
        model.add(
            sum(
                (length + kerf) * per_bar[index, batch]
                for index, length in enumerate(lengths)
            )
            <= batch_stock
        )

    for index, length in enumerate(lengths):
        model.add(
            sum(produced[index, batch] for batch in range(batch_count))
            == demand[length]
        )

    model.add(sum(multiplicity) >= min_bars)
    model.add(sum(multiplicity) <= max_bars)

    # Batch slots are interchangeable. Every solution can be reordered this way.
    for batch in range(batch_count - 1):
        model.add(multiplicity[batch] >= multiplicity[batch + 1])

    cuts = sum(per_bar.values())
    total_stock = sum(stock_total)
    type_groups = sum(present.values())
    return _ModelVariables(
        model=model,
        multiplicity=multiplicity,
        stock=stock,
        stock_total=stock_total,
        per_bar=per_bar,
        cuts=cuts,
        total_stock=total_stock,
        type_groups=type_groups,
    )


def _new_solver(time_limit_seconds: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    return solver


def _add_solution_hints(
    variables: _ModelVariables,
    solver: cp_model.CpSolver,
) -> None:
    variables.model.clear_hints()
    for variable in variables.multiplicity:
        variables.model.add_hint(variable, solver.value(variable))
    for variable in variables.stock:
        variables.model.add_hint(variable, solver.value(variable))
    for variable in variables.per_bar.values():
        variables.model.add_hint(variable, solver.value(variable))


def _is_solution(status: cp_model.CpSolverStatus) -> bool:
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def _extract_plan(
    variables: _ModelVariables,
    solver: cp_model.CpSolver,
    demand: Counter[int],
    kerf: int,
    status_label: str,
) -> ChannelBatchPlan:
    lengths = sorted(demand, reverse=True)
    raw_batches: list[ChannelBatch] = []
    for batch, multiplicity in enumerate(variables.multiplicity):
        pieces: list[int] = []
        for index, length in enumerate(lengths):
            pieces.extend(
                [length] * solver.value(variables.per_bar[index, batch])
            )
        raw_batches.append(
            ChannelBatch(
                stock_length=solver.value(variables.stock[batch]),
                multiplicity=solver.value(multiplicity),
                pieces_per_bar=tuple(sorted(pieces, reverse=True)),
                kerf=kerf,
            )
        )

    # Identical slots can be combined after solving, but never beyond six bars.
    grouped: dict[tuple[int, tuple[int, ...]], int] = defaultdict(int)
    for batch in raw_batches:
        grouped[batch.stock_length, batch.pieces_per_bar] += batch.multiplicity
    merged: list[ChannelBatch] = []
    for (stock_length, pieces), count in grouped.items():
        while count:
            multiplicity = min(6, count)
            merged.append(
                ChannelBatch(stock_length, multiplicity, pieces, kerf=kerf)
            )
            count -= multiplicity
    merged.sort(
        key=lambda batch: (
            -batch.multiplicity,
            -batch.stock_length,
            -batch.used_per_bar,
            batch.pieces_per_bar,
        )
    )
    plan = ChannelBatchPlan(tuple(merged), kerf=kerf, solver_status=status_label)
    validate_batch_plan(plan, demand)
    return plan


def _partitions(
    total: int,
    parts: int,
    maximum: int,
    upper: int | None = None,
) -> list[tuple[int, ...]]:
    """Return non-increasing positive partitions with a fixed part count."""

    if parts == 0:
        return [()] if total == 0 else []
    upper = min(maximum, total) if upper is None else min(upper, maximum, total)
    results: list[tuple[int, ...]] = []
    for first in range(upper, 0, -1):
        remaining = total - first
        if remaining < parts - 1 or remaining > first * (parts - 1):
            continue
        for suffix in _partitions(remaining, parts - 1, maximum, first):
            results.append((first, *suffix))
    return results


def _solve_structured_lower_bound(
    demand: Counter[int],
    *,
    kerf: int,
    max_stack: int,
    min_bars: int,
    max_bars: int,
    time_limit_seconds: float,
) -> ChannelBatchPlan | None:
    """Solve the minimum-batch case by fixing unavoidable long-piece batches."""

    long_lengths = sorted(
        (
            length
            for length in demand
            if 2 * (length + kerf) > 9000
        ),
        reverse=True,
    )
    long_batch_count = sum(
        math.ceil(demand[length] / max_stack) for length in long_lengths
    )
    long_bar_count = sum(demand[length] for length in long_lengths)
    short_batch_count = math.ceil(
        max(0, min_bars - long_bar_count) / max_stack
    )
    if short_batch_count == 0:
        return None

    long_options: list[list[tuple[int, ...]]] = []
    for length in long_lengths:
        parts = math.ceil(demand[length] / max_stack)
        long_options.append(_partitions(demand[length], parts, max_stack))

    short_options: list[tuple[int, ...]] = []
    minimum_short_bars = max(short_batch_count, min_bars - long_bar_count)
    maximum_short_bars = min(
        short_batch_count * max_stack,
        max_bars - long_bar_count,
    )
    for short_bars in range(minimum_short_bars, maximum_short_bars + 1):
        short_options.extend(
            _partitions(short_bars, short_batch_count, max_stack)
        )
    if not short_options:
        return None

    combinations = list(product(*long_options, short_options))
    seconds_per_combination = max(
        1.0,
        min(10.0, time_limit_seconds / max(1, len(combinations))),
    )
    short_lengths = [length for length in sorted(demand, reverse=True) if length not in long_lengths]
    best: tuple[int, ChannelBatchPlan] | None = None

    for combination in combinations:
        specs: list[tuple[int, int]] = []
        for length, multiplicities in zip(long_lengths, combination[:-1]):
            specs.extend((length, multiplicity) for multiplicity in multiplicities)
        specs.extend((0, multiplicity) for multiplicity in combination[-1])
        if len(specs) != long_batch_count + short_batch_count:
            continue
        specs.sort(key=lambda item: (-item[1], -item[0]))

        model = cp_model.CpModel()
        stock_vars: list[cp_model.IntVar] = []
        quantities: dict[tuple[int, int], cp_model.IntVar] = {}
        present: dict[tuple[int, int], cp_model.BoolVar] = {}
        for batch, (base, multiplicity) in enumerate(specs):
            is_9000 = model.new_bool_var(f"is9_{batch}")
            stock = model.new_int_var(6000, 9000, f"stock_{batch}")
            model.add(stock == 6000 + 3000 * is_9000)
            if base + kerf > 6000:
                model.add(is_9000 == 1)
            stock_vars.append(stock)
            fixed = base + kerf if base else 0
            batch_quantities = []
            for index, length in enumerate(short_lengths):
                maximum = min(
                    demand[length] // multiplicity,
                    (9000 - fixed) // (length + kerf),
                )
                quantity = model.new_int_var(0, maximum, f"q_{index}_{batch}")
                exists = model.new_bool_var(f"y_{index}_{batch}")
                model.add(quantity >= exists)
                model.add(quantity <= maximum * exists)
                quantities[index, batch] = quantity
                present[index, batch] = exists
                batch_quantities.append((length + kerf) * quantity)
            model.add(fixed + sum(batch_quantities) <= stock)

        for index, length in enumerate(short_lengths):
            model.add(
                sum(
                    specs[batch][1] * quantities[index, batch]
                    for batch in range(len(specs))
                )
                == demand[length]
            )

        cuts = long_batch_count + sum(quantities.values())
        total_stock = sum(
            specs[batch][1] * stock_vars[batch]
            for batch in range(len(specs))
        )
        type_groups = long_batch_count + sum(present.values())
        maximum_groups = len(specs) * (len(demand) + 1)
        material_weight = maximum_groups + 1
        cut_weight = (max_bars * 9000 + 1) * material_weight
        objective = cuts * cut_weight + total_stock * material_weight + type_groups
        model.minimize(objective)

        solver = _new_solver(seconds_per_combination)
        status = solver.solve(model)
        if not _is_solution(status):
            continue

        batches: list[ChannelBatch] = []
        for batch, (base, multiplicity) in enumerate(specs):
            pieces = [base] if base else []
            for index, length in enumerate(short_lengths):
                pieces.extend([length] * solver.value(quantities[index, batch]))
            batches.append(
                ChannelBatch(
                    solver.value(stock_vars[batch]),
                    multiplicity,
                    tuple(sorted(pieces, reverse=True)),
                    kerf=kerf,
                )
            )
        plan = ChannelBatchPlan(
            tuple(batches),
            kerf=kerf,
            solver_status=f"structured:{solver.status_name(status)}",
        )
        validate_batch_plan(plan, demand)
        score = int(round(solver.objective_value))
        if best is None or score < best[0]:
            best = (score, plan)

    return best[1] if best else None


def _hint_plan(
    variables: _ModelVariables,
    plan: ChannelBatchPlan,
    demand: Counter[int],
) -> None:
    variables.model.clear_hints()
    lengths = sorted(demand, reverse=True)
    batches = sorted(
        plan.batches,
        key=lambda batch: (
            -batch.multiplicity,
            -batch.stock_length,
            -batch.used_per_bar,
            batch.pieces_per_bar,
        ),
    )
    for index, batch in enumerate(batches):
        variables.model.add_hint(
            variables.multiplicity[index],
            batch.multiplicity,
        )
        variables.model.add_hint(variables.stock[index], batch.stock_length)
        per_bar_counts = Counter(batch.pieces_per_bar)
        for length_index, length in enumerate(lengths):
            variables.model.add_hint(
                variables.per_bar[length_index, index],
                per_bar_counts[length],
            )


def improve_channel_batch_plan(
    demand: Counter[int],
    initial_plan: ChannelBatchPlan,
    *,
    min_bars: int = 69,
    max_bars: int = 72,
    max_stack: int = 6,
    stock_lengths: tuple[int, ...] = (6000, 9000),
    time_limit_seconds: float = 300.0,
) -> ChannelBatchPlan:
    """Keep batch count and saw strokes fixed while reducing stock length."""

    validate_batch_plan(initial_plan, demand)
    variables = _build_model(
        demand,
        batch_count=initial_plan.batch_count,
        kerf=initial_plan.kerf,
        max_stack=max_stack,
        min_bars=min_bars,
        max_bars=max_bars,
        stock_lengths=stock_lengths,
    )
    variables.model.add(variables.cuts == initial_plan.saw_strokes)
    _hint_plan(variables, initial_plan, demand)
    variables.model.minimize(variables.total_stock)
    stock_solver = _new_solver(time_limit_seconds)
    stock_status = stock_solver.solve(variables.model)
    if not _is_solution(stock_status):
        return initial_plan

    best_stock = int(round(stock_solver.objective_value))
    stock_plan = _extract_plan(
        variables,
        stock_solver,
        demand,
        initial_plan.kerf,
        f"fixed-labor-stock:{stock_solver.status_name(stock_status)}",
    )

    variables.model.add(variables.total_stock == best_stock)
    _add_solution_hints(variables, stock_solver)
    variables.model.minimize(variables.type_groups)
    simple_solver = _new_solver(time_limit_seconds)
    simple_status = simple_solver.solve(variables.model)
    if not _is_solution(simple_status):
        return stock_plan
    return _extract_plan(
        variables,
        simple_solver,
        demand,
        initial_plan.kerf,
        (
            f"fixed-labor-stock:{stock_solver.status_name(stock_status)},"
            f"simplicity:{simple_solver.status_name(simple_status)}"
        ),
    )


def optimize_channel_batches(
    demand: Counter[int],
    *,
    kerf: int = 3,
    max_stack: int = 6,
    min_bars: int = 69,
    max_bars: int = 72,
    stock_lengths: tuple[int, ...] = (6000, 9000),
    time_limit_seconds: float = 300.0,
) -> ChannelBatchPlan:
    """Optimize whole-bar batches using labor-first lexicographic objectives."""

    demand = Counter({length: count for length, count in demand.items() if count})
    if not demand or any(length <= 0 or count <= 0 for length, count in demand.items()):
        raise ValueError("demand must contain positive lengths and quantities")
    if kerf < 0:
        raise ValueError("kerf must be non-negative")
    if max_stack < 1:
        raise ValueError("max_stack must be positive")
    if min_bars < 1 or max_bars < min_bars:
        raise ValueError("bar bounds are invalid")
    stock_lengths = tuple(sorted(set(stock_lengths)))
    if not stock_lengths or any(length <= 0 for length in stock_lengths):
        raise ValueError("stock_lengths must contain positive lengths")
    if any(length + kerf > max(stock_lengths) for length in demand):
        raise ValueError("a demanded length exceeds available stock")

    total_effective = sum((length + kerf) * count for length, count in demand.items())
    capacity_lower_bound = math.ceil(total_effective / (max(stock_lengths) * max_stack))
    bar_lower_bound = math.ceil(min_bars / max_stack)
    long_lengths = [
        length for length in demand if 2 * (length + kerf) > 9000
    ]
    long_batch_lower_bound = sum(
        math.ceil(demand[length] / max_stack) for length in long_lengths
    )
    long_bar_count = sum(demand[length] for length in long_lengths)
    short_batch_lower_bound = math.ceil(
        max(0, min_bars - long_bar_count) / max_stack
    )
    structural_lower_bound = long_batch_lower_bound + short_batch_lower_bound
    first_batch_count = max(
        capacity_lower_bound,
        bar_lower_bound,
        structural_lower_bound,
    )

    structured_applicable = (
        stock_lengths == (6000, 9000)
        and short_batch_lower_bound > 0
        and first_batch_count == structural_lower_bound
    )
    if structured_applicable:
        structured_plan = _solve_structured_lower_bound(
            demand,
            kerf=kerf,
            max_stack=max_stack,
            min_bars=min_bars,
            max_bars=max_bars,
            time_limit_seconds=time_limit_seconds,
        )
        if structured_plan is not None:
            return structured_plan

    loop_start = first_batch_count + 1 if structured_applicable else first_batch_count
    for batch_count in range(loop_start, max_bars + 1):
        variables = _build_model(
            demand,
            batch_count=batch_count,
            kerf=kerf,
            max_stack=max_stack,
            min_bars=min_bars,
            max_bars=max_bars,
            stock_lengths=stock_lengths,
        )

        # Phase 1: minimum saw strokes for the minimum feasible handling cycles.
        variables.model.minimize(variables.cuts)
        solver = _new_solver(time_limit_seconds)
        status = solver.solve(variables.model)
        if not _is_solution(status):
            continue
        best_cuts = int(round(solver.objective_value))
        best_solver = solver
        status_parts = [f"cuts:{solver.status_name(status)}"]

        # Phase 2: keep labor fixed and minimize purchased stock length.
        _add_solution_hints(variables, solver)
        variables.model.add(variables.cuts == best_cuts)
        variables.model.minimize(variables.total_stock)
        stock_solver = _new_solver(time_limit_seconds)
        stock_status = stock_solver.solve(variables.model)
        if _is_solution(stock_status):
            best_stock = int(round(stock_solver.objective_value))
            best_solver = stock_solver
            status_parts.append(f"stock:{stock_solver.status_name(stock_status)}")

            # Phase 3: with labor and material fixed, simplify batch patterns.
            _add_solution_hints(variables, stock_solver)
            variables.model.add(variables.total_stock == best_stock)
            variables.model.minimize(variables.type_groups)
            simple_solver = _new_solver(time_limit_seconds)
            simple_status = simple_solver.solve(variables.model)
            if _is_solution(simple_status):
                best_solver = simple_solver
                status_parts.append(
                    f"simplicity:{simple_solver.status_name(simple_status)}"
                )

        return _extract_plan(
            variables,
            best_solver,
            demand,
            kerf,
            ",".join(status_parts),
        )

    raise RuntimeError("no feasible channel batch plan found within bar bounds")
