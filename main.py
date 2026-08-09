import json
import os
import time
from data_parser import DataParser
from ilp import solve_mip
from simulated_annealing import simulated_annealing

def format_slot(slot_global_id: int, days: list, slots_per_day: int) -> str:
    day_idx = slot_global_id // slots_per_day
    slot_idx = slot_global_id % slots_per_day
    return f"{days[day_idx]}-{slot_idx + 1}"

def generate_report(result: dict, data: dict, parser: DataParser) -> dict:    
    assignment = result['assignment']
    days = data['days']
    slots_per_day = data['slots_per_day']
    total_slots = data['total_slots']
    teachers = data['teacher_ids']
    groups = data['group_ids']
    our_slots = data['our_slots']
    max_load = data['max_load']
    
    report = {
        'metadata': {'semester': parser.raw['metadata'].get('semester', '?'),},
        'summary': {},
        'by_teacher': {},
        'by_group': {},
        'by_day': {},
        'issues': [],
    }
    
    total_pairs = len(assignment)
    report['summary']['total_pairs'] = total_pairs
    report['summary']['teachers_used'] = len(set(assignment.values()))
    report['summary']['groups_assigned'] = len(set(g for (g, _) in assignment.keys()))
    
    for p in teachers:
        pairs = [(g, s) for (g, s), p_ in assignment.items() if p_ == p]
        if not pairs:
            continue
        
        schedule = {}
        for (g, s) in pairs:
            slot_name = format_slot(s, days, slots_per_day)
            schedule[slot_name] = g
        
        windows = 0
        for d_idx, d in enumerate(days):
            day_start = d_idx * slots_per_day
            day_end = day_start + slots_per_day
            day_slots = sorted([s for (g, s) in pairs if day_start <= s < day_end])
            if len(day_slots) >= 2:
                windows += (day_slots[-1] - day_slots[0] + 1) - len(day_slots)
        
        load_by_day = {}
        for d_idx, d in enumerate(days):
            day_start = d_idx * slots_per_day
            day_end = day_start + slots_per_day
            load_by_day[d] = sum(1 for (g, s) in pairs if day_start <= s < day_end)
        
        report['by_teacher'][p] = {
            'total_pairs': len(pairs),
            'max_load': max_load.get(p, 0),
            'groups': list(set(g for (g, _) in pairs)),
            'windows': windows,
            'load_by_day': load_by_day,
            'schedule': dict(sorted(schedule.items())),
        }
    
    for g in groups:
        g_pairs = [(s, p) for (g_, s), p in assignment.items() if g_ == g]
        if not g_pairs:
            group_slots = sorted([s for (g_, s) in our_slots if g_ == g])
            report['by_group'][g] = {
                'teacher': 'НЕ НАЗНАЧЕН',
                'slots': [format_slot(s, days, slots_per_day) for s in group_slots],
                'total_pairs': len(group_slots),
            }
        else:
            teacher = g_pairs[0][1]
            slots = sorted([s for (s, _) in g_pairs])
            report['by_group'][g] = {
                'teacher': teacher,
                'slots': [format_slot(s, days, slots_per_day) for s in slots],
                'total_pairs': len(slots),
            }
    
    issues = []
    unassigned = []
    for (g, s) in our_slots:
        if (g, s) not in assignment:
            unassigned.append(format_slot(s, days, slots_per_day))
    if unassigned:
        issues.append({
            'type': 'unassigned_slots',
            'count': len(unassigned),
            'details': unassigned[:10],
        })
    
    if result.get('room_violations'):
        issues.append({
            'type': 'room_violations',
            'count': len(result['room_violations']),
            'details': [
                {'slot': format_slot(s, days, slots_per_day), 'excess': v}
                for (s, v) in result['room_violations']
            ],
        })
    
    lost = result.get('lost_groups', [])
    if lost:
        issues.append({
            'type': 'lost_groups',
            'count': len(lost),
            'details': [{'teacher': p, 'group': g} for (p, g) in lost],
        })
    
    report['issues'] = issues
    return report


def save_results(result: dict, data: dict, parser: DataParser, input_path: str):    
    os.makedirs('output', exist_ok=True)
    
    report = generate_report(result, data, parser)
    
    report_path = f'output/report.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # краткая версия
    days = data['days']
    slots_per_day = data['slots_per_day']
    short = {
        'semester': parser.raw['metadata'].get('semester', '?'),
        'assignments': {},
    }
    for (g, s), p in sorted(result['assignment'].items()):
        slot_name = format_slot(s, days, slots_per_day)
        short['assignments'][f"{g} | {slot_name}"] = p
    
    short_path = f'output/assignments.json'
    with open(short_path, 'w', encoding='utf-8') as f:
        json.dump(short, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены:")
    print(f"  Полный отчёт: {report_path}")
    print(f"  Назначения:    {short_path}")
    
    return report


def print_schedule(result: dict, data: dict):    
    days = data['days']
    slots_per_day = data['slots_per_day']
    teachers = data['teacher_ids']
    
    print("\n" + "="*30)
    print("итоговое расписание по преподавателям")
    print("="*30)
    
    for p in teachers:
        pairs = [(g, s) for (g, s), p_ in result['assignment'].items() if p_ == p]
        if not pairs:
            print(f"\n{p}: нет назначений")
            continue
        
        print(f"\n{p} ({len(pairs)} пар):")
        
        for d_idx, d in enumerate(days):
            day_pairs = [(g, s) for (g, s) in pairs
                        if d_idx * slots_per_day <= s < (d_idx + 1) * slots_per_day]
            if day_pairs:
                slots_str = ", ".join(
                    f"{s % slots_per_day + 1}п({g})"
                    for (g, s) in sorted(day_pairs, key=lambda x: x[1])
                )
                print(f"  {d}: {slots_str}")
            else:
                print(f"  {d}: —" if any((g, s) for (g, s) in pairs 
                                         if d_idx * slots_per_day <= s < (d_idx + 1) * slots_per_day) 
                      else f"  {d}: выходной")


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    filename = "input.json"
    input_path = os.path.join(project_root, filename)
    
    print(f"загрузка данных из: {input_path}")
    
    parser = DataParser(input_path)
    parser.print_summary()
    data = parser.get_data()
    t_start = time.time()
    mip_result = solve_mip(data)
    t_mip = time.time() - t_start
    print(f"\n время выполнения ЦЛП: {t_mip*1000:.0f} мс")

    t_start = time.time()
    sa_result = simulated_annealing(mip_result,data,max_iter=20000,T_start=1000.0,T_min=0.01,alpha=0.995)
    t_sa = time.time() - t_start
    print(f"\n время выполнения отжига: {t_sa*1000:.0f} мс")

    report = save_results(sa_result, data, parser, input_path)
    print_schedule(sa_result, data)

    print("\n----- итог")
    n_teachers_used = len(set(sa_result['assignment'].values()))
    n_groups = len(set(g for (g, _) in sa_result['assignment'].keys()))
    
    total_windows = sum(t_data.get('windows', 0) for t_data in report['by_teacher'].values())
    
    print(f"  Назначено пар: {len(sa_result['assignment'])}")
    print(f"  Задействовано преподавателей: {n_teachers_used}")
    print(f"  Групп с назначениями: {n_groups}")
    print(f"  Всего окон у преподавателей: {total_windows}")
    print(f"  Нарушений RoomLimit: {len(sa_result['room_violations'])}")
    print(f"  Потеряно своих групп: {len(mip_result.get('lost_groups', []))}")


if __name__ == '__main__':
    main()