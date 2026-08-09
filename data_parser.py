import json

class DataParser:    
    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.raw = json.load(f)
        self._validate()
        self._parse()
    
    def _validate(self):
        raw = self.raw
        # Проверка metadata
        if 'metadata' not in raw:
            raise ValueError("Отсутствует секция 'metadata'")
        meta = raw['metadata']
        required_meta = ['days', 'slots_per_day', 'room_limit']
        for key in required_meta:
            if key not in meta:
                raise ValueError(f"В metadata отсутствует '{key}'")
        # Проверка teachers
        if 'teachers' not in raw:
            raise ValueError("Отсутствует 'teachers'")
        for t in raw['teachers']:
            if 'id' not in t or 'max_load' not in t or 'wish_days_off' not in t:
                raise ValueError(f"У преподавателя {t.get('name', '?')} неполные данные")
        # Проверка groups
        if 'groups' not in raw:
            raise ValueError("Отсутствует 'groups'")
        days = meta['days']
        slots_per_day = meta['slots_per_day']
        expected_length = len(days)
        expected_inner = slots_per_day
        for g_name, schedule in raw['groups'].items():
            if len(schedule) != expected_length:
                raise ValueError(
                    f"У группы {g_name} количество строк ({len(schedule)}) "
                    f"не совпадает с количеством дней ({expected_length})"
                )
            for i, row in enumerate(schedule):
                if len(row) != expected_inner:
                    raise ValueError(
                        f"У группы {g_name}, день {days[i]}: "
                        f"количество слотов ({len(row)}) не совпадает "
                        f"со slots_per_day ({expected_inner})"
                    )
        # Проверка previous_semester
        if 'previous_semester' not in raw:
            raw['previous_semester'] = {}
        # Проверка ставок
        total_load = sum(t['max_load'] for t in raw['teachers'])
        total_our = sum(
            1 for g in raw['groups'].values()
            for row in g for cell in row
            if cell in ('OUR', 'our', 'ИНЯЗ', 'иняз')
        )
        print(f"  Суммарная ставка: {total_load}, пар ИНЯЗ: {total_our}")
        if total_our > total_load:
            print(f"  пар больше чем ставка на {total_our - total_load}")
        elif total_our < total_load:
            print(f"  ставка больше чем пар на {total_load - total_our}")
    
    def _parse(self):
        raw = self.raw
        meta = raw['metadata']
        
        self.days = meta['days']
        self.slots_per_day = meta['slots_per_day']
        self.total_slots = len(self.days) * self.slots_per_day
        self.room_limit = meta['room_limit']
        
        self.teacher_ids = []
        self.max_load = {}
        self.wish_days_off = {}
        
        for t in raw['teachers']:
            tid = t['id']
            self.teacher_ids.append(tid)
            self.max_load[tid] = t['max_load']
            self.wish_days_off[tid] = set(t.get('wish_days_off', []))
        
        self.group_ids = list(raw['groups'].keys())
        self.our_slots = set()
        self.free_slots = set()
        self.group_slots_count = {}
        
        # ДЕБАГ
        total_our_debug = 0
        groups_by_our_count = {}
        
        for g_name, schedule in raw['groups'].items():
            our_count = 0
            for day_idx, row in enumerate(schedule):
                for slot_idx, value in enumerate(row):
                    global_id = day_idx * self.slots_per_day + slot_idx
                    
                    if value in ('OUR', 'our'):
                        self.our_slots.add((g_name, global_id))
                        our_count += 1
                        total_our_debug += 1
                    elif value in ('FREE', 'free'):
                        self.free_slots.add((g_name, global_id))
            
            self.group_slots_count[g_name] = our_count
            if our_count not in groups_by_our_count:
                groups_by_our_count[our_count] = []
            groups_by_our_count[our_count].append(g_name)
        
        # Проверка соответствия ставке
        total_load = sum(self.max_load.values())
        print(f"\n  Всего OUR слотов: {total_our_debug}")
        print(f"  Суммарная ставка: {total_load}")
        
        if total_our_debug != total_load:
            print(f"  НЕСОВПАДЕНИЕ Разница: {total_our_debug - total_load}")
        
        # Проверка преподавателей без групп в предыдущем семестре
        teachers_with_prev = set()
        for (p_id, g_list) in raw.get('previous_semester', {}).items():
            teachers_with_prev.add(p_id)
        
        teachers_without_prev = set(self.teacher_ids) - teachers_with_prev
        if teachers_without_prev:
            print(f"\n  Преподаватели без закреплённых групп: {teachers_without_prev}")
        
        # Закрепленные группы
        self.prev_matrix = {}
        prev_data = raw.get('previous_semester', {})
        
        for p_id, group_list in prev_data.items():
            for g_name in group_list:
                if g_name not in self.group_ids:
                    print(f" Закреплённая группа {g_name} (преп. {p_id}) не найдена в расписании")
                self.prev_matrix[(p_id, g_name)] = True
        
        # Матрица пожеланий выходных
        self.wish_matrix = {}
        for t in raw['teachers']:
            tid = t['id']
            for day in self.days:
                self.wish_matrix[(tid, day)] = 0 if day in self.wish_days_off[tid] else 1
    
    def get_data(self) -> dict:
        return {
            'teacher_ids': self.teacher_ids,
            'group_ids': self.group_ids,
            'our_slots': self.our_slots,
            'free_slots': self.free_slots,
            'prev_matrix': self.prev_matrix,
            'wish_matrix': self.wish_matrix,
            'max_load': self.max_load,
            'total_slots': self.total_slots,
            'days': self.days,
            'slots_per_day': self.slots_per_day,
            'room_limit': self.room_limit,
            'group_slots_count': self.group_slots_count,
        }
    
    def print_summary(self):
        data = self.get_data()
        
        total_our = len(data['our_slots'])
        total_free = len(data['free_slots'])
        total_capacity = sum(data['max_load'].values())
        
        print(f"Семестр: {self.raw['metadata'].get('semester', '?')}")
        print(f"Дни: {', '.join(self.days)}")
        print(f"Пар в день: {self.slots_per_day}")
        print(f"Всего слотов: {self.total_slots}")
        print(f"RoomLimit: {self.room_limit}")
        print(f"Преподавателей: {len(data['teacher_ids'])}")
        print(f"Групп: {len(data['group_ids'])}")
        print(f"Пар ИНЯЗ в неделю: {total_our}")
        print(f"Свободных слотов (окон) у групп: {total_free}")
        print(f"Суммарная ставка: {total_capacity}")

        slot_load = {}
        for (g, s) in data['our_slots']:
            slot_load[s] = slot_load.get(s, 0) + 1
        max_in_slot = max(slot_load.values()) if slot_load else 0
        print(f"Максимум пар в одном слоте: {max_in_slot}")
        if max_in_slot > self.room_limit:
            print(f" Будет превышение RoomLimit на {max_in_slot - self.room_limit}")
        
        prev_count = len(data['prev_matrix'])
        if prev_count > 0:
            print(f"Закреплённых групп: {prev_count}")
            for (p, g) in sorted(data['prev_matrix'].keys()):
                print(f"  {p} → {g}")
        else:
            print(f"Закреплённых групп: 0 ")
        
        print(f"{'='*30}\n")



if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        json_file = 'input.json'
    
    parser = DataParser(json_file)
    parser.print_summary()