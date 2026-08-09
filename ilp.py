import pulp

def solve_mip(data: dict) -> dict:
    teachers = data['teacher_ids']
    groups = data['group_ids']
    our_slots = data['our_slots']
    prev = data['prev_matrix']
    wish = data['wish_matrix']
    max_load = data['max_load']
    total_slots = data['total_slots']
    days = data['days']
    slots_per_day = data['slots_per_day']
    room_limit = data['room_limit']
    group_slots_count = data['group_slots_count']
    
    print("\n1: ЦЛП")
    print("-"*30)
    prob = pulp.LpProblem("Timetable_Balanced", pulp.LpMaximize)
    
    assign = {}
    for p in teachers:
        for g in groups:
            if g in group_slots_count and group_slots_count[g] > 0:
                assign[p, g] = pulp.LpVariable(f"a_{p}_{g}", cat="Binary")
    x = {}
    for p in teachers:
        for (g, s) in our_slots:
            if (p, g) in assign:
                x[p, g, s] = pulp.LpVariable(f"x_{p}_{g}_{s}", cat="Binary")
    over = {}
    for s in range(total_slots):
        if any((g, s) in our_slots for g in groups):
            over[s] = pulp.LpVariable(f"over_{s}", lowBound=0, cat="Integer")
    works = {}
    for p in teachers:
        for d in days:
            works[p, d] = pulp.LpVariable(f"w_{p}_{d}", cat="Binary")
    unwanted = {}
    for p in teachers:
        for d in days:
            if (p, d) in wish and wish[p, d] == 0:
                unwanted[p, d] = pulp.LpVariable(f"uw_{p}_{d}", cat="Binary")
    
    print(f"  Переменных: assign={sum(1 for _ in assign)}, "
          f"x={sum(1 for _ in x)}, over={sum(1 for _ in over)}, "
          f"works={sum(1 for _ in works)}, unwanted={sum(1 for _ in unwanted)}")
    
    # жесткие ограничение
    # группа - один преподаватель
    for g in groups:
        vars_for_g = [assign[p, g] for p in teachers if (p, g) in assign]
        if vars_for_g:
            prob += pulp.lpSum(vars_for_g) == 1, f"one_{g}"
    
    # x[p,g,s] = assign[p,g]
    for p in teachers:
        for g in groups:
            if (p, g) not in assign:
                continue
            for s in range(total_slots):
                if (g, s) in our_slots:
                    prob += x[p, g, s] == assign[p, g], f"x_eq_{p}_{g}_{s}"
    
    # покрытие всех слотов
    for (g, s) in our_slots:
        prob += pulp.lpSum(x[p, g, s] for p in teachers if (p, g, s) in x) == 1, f"cov_{g}_{s}"
    
    # преподаватель в одном месте
    for p in teachers:
        for s in range(total_slots):
            vars_in_slot = [x[p, g, s] for g in groups if (g, s) in our_slots and (p, g, s) in x]
            if vars_in_slot:
                prob += pulp.lpSum(vars_in_slot) <= 1, f"nodb_{p}_{s}"
    
    # нагрузка == ставка
    for p in teachers:
        load_terms = []
        for g in groups:
            if (p, g) in assign and g in group_slots_count:
                load_terms.append(group_slots_count[g] * assign[p, g])
        if load_terms:
            prob += pulp.lpSum(load_terms) == max_load[p], f"load_{p}"
    
    # roomLimit
    for s in range(total_slots):
        vars_in_slot = [x[p, g, s] for p in teachers for g in groups 
                       if (g, s) in our_slots and (p, g, s) in x]
        if vars_in_slot:
            prob += pulp.lpSum(vars_in_slot) <= room_limit + over[s], f"room_{s}"
    
    # works + assign
    for p in teachers:
        for d_idx, d in enumerate(days):
            day_start = d_idx * slots_per_day
            day_end = day_start + slots_per_day
            
            related_groups = [
                g for g in groups
                if any(day_start <= s < day_end 
                      for s in range(total_slots) if (g, s) in our_slots)
                and (p, g) in assign
            ]
            
            if not related_groups:
                prob += works[p, d] == 0, f"w_zero_{p}_{d}"
                continue
            
            for g in related_groups:
                prob += works[p, d] >= assign[p, g], f"w_ge_{p}_{d}_{g}"
            
            prob += works[p, d] <= pulp.lpSum(assign[p, g] for g in related_groups), f"w_le_{p}_{d}"
    
    # unwanted + works
    for p in teachers:
        for d in days:
            if (p, d) in wish and wish[p, d] == 0:
                prob += unwanted[p, d] == works[p, d], f"uw_eq_{p}_{d}"
    
    # сохранение группы
    obj_continuity = pulp.lpSum(assign[p, g] for (p, g) in prev if (p, g) in assign)
    # работа в выходной день
    obj_unwanted = pulp.lpSum(unwanted[p, d] for (p, d) in unwanted)
    # roomLimit
    obj_over = pulp.lpSum(over[s] for s in over)
    
    W_CONT = 5000 
    W_UNWANTED = -2000
    W_OVER = -3000 
    
    prob += (W_CONT * obj_continuity + W_UNWANTED * obj_unwanted + W_OVER * obj_over)
    prob.solve(pulp.PULP_CBC_CMD(msg=True, timeLimit=120, gapRel=0.01))
    
    status = pulp.LpStatus[prob.status]
    print(f"\n  Статус: {status}")    
    
    assignment = {}
    for g in groups:
        for p in teachers:
            if (p, g) in assign:
                val = pulp.value(assign[p, g])
                if val is not None and val > 0.5:
                    for s in range(total_slots):
                        if (g, s) in our_slots:
                            assignment[(g, s)] = p
                    break
    
    # статистика
    saved_groups = []
    lost_groups = []
    for (p, g) in prev:
        if (p, g) in assign:
            val = pulp.value(assign[p, g])
            if val is not None and val > 0.5:
                saved_groups.append((p, g))
            else:
                lost_groups.append((p, g))
    
    room_violations = []
    for s in over:
        val = pulp.value(over[s])
        if val is not None and val > 0.5:
            room_violations.append((s, int(val)))
    
    unwanted_days_worked = []
    for (p, d) in unwanted:
        val = pulp.value(unwanted[p, d])
        if val is not None and val > 0.5:
            unwanted_days_worked.append((p, d))
    
    obj_val = pulp.value(prob.objective)
    
    print(f"\n  ----- результаты цлп: ")
    print(f"  значение целевой функции: {obj_val:.0f}")
    print(f"  сохранено своих групп: {len(saved_groups)}/{len(prev)}")
    if lost_groups:
        print(f"  потеряно своих групп: {len(lost_groups)}")
    else:
        print(f"  все свои группы сохранены")
    
    print(f"  нарушений RoomLimit: {len(room_violations)}")
    if room_violations:
        for (s, v) in room_violations:
            day = s // slots_per_day
            slot_idx = s % slots_per_day
            print(f"    {days[day]}-{slot_idx+1}: +{v}")
    
    print(f"  работа в выходные дни: {len(unwanted_days_worked)}")
    if unwanted_days_worked:
        for (p, d) in unwanted_days_worked:
            print(f"    {p} → {d}")
    
    # проверка
    print(f"\n  ----- проверка")
    all_groups_with_teacher = set()
    for (g, s), p in assignment.items():
        all_groups_with_teacher.add((g, p))
    group_teacher_count = {}
    for (g, p) in all_groups_with_teacher:
        if g not in group_teacher_count:
            group_teacher_count[g] = []
        group_teacher_count[g].append(p)
    broken_groups = {g: ps for g, ps in group_teacher_count.items() if len(ps) > 1}
    if broken_groups:
        print(f"  нарушение: {len(broken_groups)} групп имеют >1 преподавателя")
        for g, ps in broken_groups.items():
            print(f"    {g}: {ps}")
    else:
        print(f"  все группы имеют ровно одного преподавателя")
    
    print(f"  всего назначено слотов: {len(assignment)} из {len(our_slots)}")
    
    return {
        'assignment': assignment,
        'room_violations': room_violations,
        'lost_groups': lost_groups,
        'saved_groups': saved_groups,
        'unwanted_days': unwanted_days_worked,
        'objective_value': obj_val,
        'status': status,
    }