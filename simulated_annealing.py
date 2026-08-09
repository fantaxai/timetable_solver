import random
import math
import copy


def simulated_annealing(mip_solution: dict, data: dict, max_iter: int = 20000, T_start: float = 1000.0, 
                        T_min: float = 0.01, alpha: float = 0.995) -> dict:
    teachers = data['teacher_ids']
    groups = data['group_ids']
    our_slots = data['our_slots']
    free_slots_set = data['free_slots']
    prev = data['prev_matrix']
    wish = data['wish_matrix']
    max_load = data['max_load']
    days = data['days']
    slots_per_day = data['slots_per_day']
    total_slots = data['total_slots']
    room_limit = data['room_limit']
    
    print("2: имитация отжига")
    print("-"*30)
    
     
    def build_state(assignment):
        state = dict(assignment)
        t_slots = {p: set() for p in teachers}
        s_occ = {s: [] for s in range(total_slots)}
        
        for (g, s), p in state.items():
            t_slots[p].add((g, s))
            s_occ[s].append((g, p))
        
        return state, t_slots, s_occ
    
    current, teacher_slots, slot_occupancy = build_state(mip_solution['assignment'])
    
    def energy(state, t_slots, s_occ, phase='early'):
        E = 0
        
        # жесткие нарушения
        # двойное бронирование
        for p in teachers:
            slots_used = {}
            for (g, s) in t_slots[p]:
                if s in slots_used:
                    E += 10000
                slots_used[s] = True
        # RoomLimit
        for s in range(total_slots):
            excess = len(s_occ[s]) - room_limit
            if excess > 0:
                E += 10000 * excess
        # превышение нагрузки
        for p in teachers:
            excess = len(t_slots[p]) - max_load[p]
            if excess > 0:
                E += 10000 * excess
        
        # мягкие ограничения
        # потеря своих групп
        for p in teachers:
            for g in groups:
                if (p, g) in prev:
                    has_group = any(g_ == g for (g_, _) in t_slots[p])
                    if not has_group:
                        E += 100
        # нежелательные дни
        for p in teachers:
            worked_days = set()
            for (g, s) in t_slots[p]:
                day = days[s // slots_per_day]
                worked_days.add(day)
            for d in worked_days:
                if (p, d) in wish and wish[p, d] == 0:
                    E += 50
        # окна и равномерность
        if phase == 'early':
            w_windows, w_balance = 10, 5
        else:
            w_windows, w_balance = 40, 30
        
        # окна
        for p in teachers:
            for d_idx in range(len(days)):
                day_start = d_idx * slots_per_day
                day_end = day_start + slots_per_day
                day_slots = sorted([s for (g, s) in t_slots[p]
                                   if day_start <= s < day_end])
                if len(day_slots) >= 2:
                    windows = (day_slots[-1] - day_slots[0] + 1) - len(day_slots)
                    E += w_windows * windows
        
        # неравномерность
        for p in teachers:
            loads = []
            for d_idx in range(len(days)):
                day_start = d_idx * slots_per_day
                day_end = day_start + slots_per_day
                load = sum(1 for (g, s) in t_slots[p] if day_start <= s < day_end)
                loads.append(load)
            if sum(loads) > 0:
                avg = sum(loads) / len(loads)
                E += w_balance * sum(abs(l - avg) for l in loads)
        return E
    
    
    def shift_operator(state, t_slots, s_occ):
        new_state = dict(state)
        new_t_slots = {p: set(ts) for p, ts in t_slots.items()}
        new_s_occ = {s: list(lst) for s, lst in s_occ.items()}
        
        all_pairs = list(state.items())
        if not all_pairs:
            return new_state, new_t_slots, new_s_occ
        
        random.shuffle(all_pairs)
        for (g, old_slot), p in all_pairs:
            free_slots = [s for s in range(total_slots)
                         if (g, s) in free_slots_set
                         and not any(p_ == p for (_, p_) in new_s_occ[s])
                         and len(new_s_occ[s]) < room_limit]
            
            if free_slots:
                new_slot = random.choice(free_slots)
                
                del new_state[(g, old_slot)]
                new_t_slots[p].discard((g, old_slot))
                new_s_occ[old_slot] = [(g_, p_) for (g_, p_) in new_s_occ[old_slot] if not (g_ == g and p_ == p)]
                
                new_state[(g, new_slot)] = p
                new_t_slots[p].add((g, new_slot))
                new_s_occ[new_slot].append((g, p))
                
                return new_state, new_t_slots, new_s_occ
        return new_state, new_t_slots, new_s_occ
    
    def swap_groups_operator(state, t_slots, s_occ):
        new_state = dict(state)
        new_t_slots = {p: set(ts) for p, ts in t_slots.items()}
        new_s_occ = {s: list(lst) for s, lst in s_occ.items()}
        
        p1, p2 = random.sample(teachers, 2)
        groups_p1 = set(g for (g, _) in new_t_slots[p1])
        groups_p2 = set(g for (g, _) in new_t_slots[p2])
        
        if not groups_p1 or not groups_p2:
            return new_state, new_t_slots, new_s_occ
        
        g1 = random.choice(list(groups_p1))
        g2 = random.choice(list(groups_p2))
        
        if g1 == g2:
            return new_state, new_t_slots, new_s_occ
        slots_g1 = set(s for (g, s) in new_t_slots[p1] if g == g1)
        slots_g2 = set(s for (g, s) in new_t_slots[p2] if g == g2)
        
        p2_conflict = any(
            any(p_ == p2 for (_, p_) in new_s_occ[s]) for s in slots_g1
        )
        p1_conflict = any(
            any(p_ == p1 for (_, p_) in new_s_occ[s]) for s in slots_g2
        )
        
        if p2_conflict or p1_conflict:
            return new_state, new_t_slots, new_s_occ
        
        for s in slots_g1:
            if len(new_s_occ[s]) - 1 + 1 > room_limit:
                return new_state, new_t_slots, new_s_occ
        for s in slots_g2:
            if len(new_s_occ[s]) - 1 + 1 > room_limit:
                return new_state, new_t_slots, new_s_occ
        
        for s in slots_g1:
            del new_state[(g1, s)]
            new_t_slots[p1].discard((g1, s))
            new_s_occ[s] = [(g_, p_) for (g_, p_) in new_s_occ[s]
                           if not (g_ == g1 and p_ == p1)]
        
        for s in slots_g2:
            del new_state[(g2, s)]
            new_t_slots[p2].discard((g2, s))
            new_s_occ[s] = [(g_, p_) for (g_, p_) in new_s_occ[s]
                           if not (g_ == g2 and p_ == p2)]
        
        for s in slots_g1:
            new_state[(g1, s)] = p2
            new_t_slots[p2].add((g1, s))
            new_s_occ[s].append((g1, p2))
        
        for s in slots_g2:
            new_state[(g2, s)] = p1
            new_t_slots[p1].add((g2, s))
            new_s_occ[s].append((g2, p1))
        
        return new_state, new_t_slots, new_s_occ
    
    
    current_E = energy(current, teacher_slots, slot_occupancy, 'early')
    best_state = copy.deepcopy(current)
    best_t_slots = {p: set(ts) for p, ts in teacher_slots.items()}
    best_s_occ = {s: list(lst) for s, lst in slot_occupancy.items()}
    best_E = current_E
    
    T = T_start
    phase = 'early'
    no_improve = 0
    
    for iteration in range(max_iter):
        has_overload = any(
            len(slot_occupancy[s]) > room_limit
            for s in range(total_slots)
        )
        
        if has_overload:
            if random.random() < 0.6:
                new_state, new_t_slots, new_s_occ = shift_operator(current, teacher_slots, slot_occupancy)
            else:
                new_state, new_t_slots, new_s_occ = swap_groups_operator(current, teacher_slots, slot_occupancy)
        else:
            new_state, new_t_slots, new_s_occ = swap_groups_operator(current, teacher_slots, slot_occupancy)
        
        new_E = energy(new_state, new_t_slots, new_s_occ, phase)
        delta = new_E - current_E
        
        if delta < 0 or random.random() < math.exp(-delta / max(T, 0.001)):
            current = new_state
            teacher_slots = new_t_slots
            slot_occupancy = new_s_occ
            current_E = new_E
            
            if current_E < best_E:
                best_state = copy.deepcopy(current)
                best_t_slots = {p: set(ts) for p, ts in teacher_slots.items()}
                best_s_occ = {s: list(lst) for s, lst in slot_occupancy.items()}
                best_E = current_E
                no_improve = 0
            else:
                no_improve += 1
        
        T *= alpha
        
        has_overload_best = any(len(best_s_occ[s]) > room_limit for s in range(total_slots))
        if phase == 'early' and not has_overload_best:
            phase = 'fine'
            T = 10.0
            print(f"  [итерация {iteration}] конфликты устранены → тонкая настройка")
        
        if phase == 'fine' and no_improve > 3000:
            print(f"  [итерация {iteration}] стагнация, выход")
            break
        
        if iteration % 2000 == 0:
            overload_count = sum(1 for s in range(total_slots) if len(best_s_occ[s]) > room_limit)
            print(f"  итерация {iteration}: T={T:.2f}, E={current_E:.0f}, " f"best={best_E:.0f}, конфликтов={overload_count}")

    room_violations_final = []
    for s in range(total_slots):
        excess = len(best_s_occ[s]) - room_limit
        if excess > 0:
            room_violations_final.append((s, excess))
    
    print(f"\n  этап отжига завершен:")
    print(f"  лучшая энергия: {best_E:.0f}")
    print(f"  осталось нарушений по аудиториям: {len(room_violations_final)}")
    
    return {
        'assignment': best_state,
        'room_violations': room_violations_final,
        'energy': best_E,
    }