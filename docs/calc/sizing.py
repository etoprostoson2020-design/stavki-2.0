"""Расчёты, на которые ссылается проектная документация.

Запуск:  python3 docs/calc/sizing.py
Зависимостей нет — только стандартная библиотека.

Все таблицы в docs/*.md воспроизводятся этим скриптом. Если число в документе
разошлось с выводом скрипта — прав скрипт.
"""
import math

Z95_TWO = 1.959963985   # двусторонний 95%
Z95_ONE = 1.644853627   # односторонний 95%

# Матчей за сезон. Источник — регламенты лиг; при реализации проверяется
# программно по данным API (п. 2 ТЗ: не полагаться на предположения).
LEAGUES = {
    "АПЛ (39)": 380, "Ла Лига (140)": 380, "Серия А (135)": 380,
    "Бундеслига (78)": 306, "Лига 1 (61)": 306,
    "Championship (40)": 552, "Segunda (141)": 462, "Серия B (136)": 380,
    "2.Bundesliga (79)": 306, "Ligue 2 (62)": 380,
}
TOP5 = sum(v for k, v in LEAGUES.items() if any(t in k for t in ("39)", "140)", "135)", "78)", "61)")))
ALL_LEAGUES = sum(LEAGUES.values())
SEASONS = 10
DAILY_LIMIT, HARD_STOP = 7500, 0.90


def wilson_lower(k: int, n: int, one_sided: bool = False) -> float:
    """Нижняя граница доверительного интервала Уилсона."""
    z = Z95_ONE if one_sided else Z95_TWO
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - spread) / denom


def k_breakeven(a: float, b: float) -> float:
    """Обобщённый коэффициент безубыточности, docs/04-markets.md.
    a = p_win + p_half_win/2, b = p_loss + p_half_loss/2.
    Для бинарного рынка a = p, b = 1-p, результат = 1/p."""
    return 1 + b / a


def binom_tail(k: int, n: int, p: float = 0.5) -> float:
    """Односторонний биномиальный p-value: P(X >= k)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def t1_breakeven_table() -> None:
    print("Т1. Коэффициент безубыточности и требуемый перевес над линией")
    print("    (маржа букмекера 5%; docs/05-validator.md разд. 2, docs/07 С1)")
    print(f"{'p̂':>5}{'n':>7}{'p_lower':>9}{'К точ':>8}{'К конс':>8}{'порог':>8}{'перевес':>9}")
    for phat in (0.60, 0.55, 0.50, 0.35):
        for n in (50, 100, 200, 500, 1000, 3000):
            k = round(phat * n)
            lo = wilson_lower(k, n)
            thr = 1.05 / lo
            market = (1 / phat) / 1.05
            print(f"{phat:>5.2f}{n:>7}{lo:>9.4f}{1/(k/n):>8.3f}{1/lo:>8.3f}{thr:>8.3f}{thr/market-1:>8.0%}")
        print()


def t2_one_sided() -> None:
    print("Т2. Односторонний интервал против двустороннего (docs/07 С1б)")
    print(f"{'p̂':>5}{'n':>7}{'К 2-стор':>10}{'К 1-стор':>10}{'выигрыш':>9}")
    for phat in (0.60, 0.55):
        for n in (50, 100, 200, 500, 1000):
            k = round(phat * n)
            k2, k1 = 1 / wilson_lower(k, n), 1 / wilson_lower(k, n, one_sided=True)
            print(f"{phat:>5.2f}{n:>7}{k2:>10.3f}{k1:>10.3f}{1-k1/k2:>8.1%}")
        print()


def t3_per_window() -> None:
    total = ALL_LEAGUES * SEASONS
    print(f"Т3. Разбивка выборки по девяти OOS-окнам ({total} матчей, docs/07 С2)")
    print(f"{'n всего':>9}{'доля':>8}{'на окно':>9}{'95% ДИ при p̂=0.60':>22}")
    for n in (50, 200, 500):
        per = max(round(n / 9), 1)
        k = round(0.60 * per)
        lo, z = wilson_lower(k, per), Z95_TWO
        p = k / per
        hi = (p + z*z/(2*per) + z*math.sqrt(p*(1-p)/per + z*z/(4*per*per))) / (1 + z*z/per)
        print(f"{n:>9}{n/total:>8.2%}{per:>9}   [{lo:.2f}, {hi:.2f}] ширина {(hi-lo)*100:.0f} п.п.")
    print()


def t4_volume() -> None:
    total = ALL_LEAGUES * SEASONS
    print("Т4. Объём данных (docs/01 Р1)")
    print(f"    матчей за сезон: топ-5 {TOP5}, все десять лиг {ALL_LEAGUES}")
    print(f"    за {SEASONS} сезонов: {total} матчей, {total*2} строк витрины")
    print(f"    200 признаков float32: {200*4*total*2/1e6:.0f} МБ — помещается в память целиком")
    words = math.ceil(total / 64)
    print(f"    битовая маска: {words} слов uint64 = {words*8} байт на гипотезу")
    print()


def t5_api_budget() -> None:
    print(f"Т5. Бюджет API ({DAILY_LIMIT}/сут, стоп на {HARD_STOP:.0%}; docs/06)")
    effective = DAILY_LIMIT * HARD_STOP
    for label, fixtures in (("топ-5", TOP5 * SEASONS), ("топ-5 + вторые", ALL_LEAGUES * SEASONS)):
        for scen, per in (("statistics+events+lineups", 3),
                          ("events+lineups (статистика из CSV)", 2),
                          ("только events", 1)):
            req = fixtures * per + 100  # +100 — скелет календаря
            print(f"    {label:<16}{scen:<36}{req:>7} запросов = {req/effective:>5.1f} сут")
    print()


def t6_multiplicity() -> None:
    print("Т6. Поправка на множественность (docs/07 С4)")
    print("    Порог p для первой находки при FDR 10%:")
    for m in (10**3, 10**5, 10**7):
        print(f"      проверено {m:>12,} гипотез -> p <= {0.10/m:.1e}")
    print("    Достижимый односторонний биномиальный p (база 0.50):")
    for n in (200, 500, 1000):
        for phat in (0.55, 0.60):
            print(f"      n={n:>5} p̂={phat:.2f} -> p = {binom_tail(round(phat*n), n):.1e}")
    print()


def t7_mining_speed() -> None:
    total = ALL_LEAGUES * SEASONS
    words = math.ceil(total / 64)
    print("Т7. Скорость движка на битовых масках (docs/01 Р4)")
    print("    допущение: 10^9 словных операций в секунду на ядро, 3 прохода на гипотезу")
    for h in (10**5, 10**6, 10**7, 10**8):
        print(f"      {h:>12,} гипотез -> {h*words*3/1e9:>8.1f} с")
    print("    перестановочный тест с полным повтором майнинга:")
    for perms in (200, 1000):
        for h in (10**5, 10**6):
            sec = perms * h * words * 3 / 1e9
            print(f"      {perms:>5} перестановок x {h:>10,} гипотез = {sec/3600:>5.2f} ч (1 ядро), "
                  f"{sec/3600/8:>5.2f} ч (8 ядер)")
    print()


def t8_hypothesis_space() -> None:
    features, bins, markets = 150, 6, 34
    atoms = features * bins
    print(f"Т8. Пространство гипотез: {features} признаков x {bins} бинов = {atoms} условий, "
          f"{markets} рынков (docs/01 Р4)")
    for d in (1, 2, 3, 4):
        c = math.comb(atoms, d)
        print(f"      глубина {d}: {c:>18,} комбинаций x {markets} = {c*markets:>20,} гипотез")
    print("    Отсечение по поддержке (Apriori) сокращает реальный перебор до 10^5-10^7.")
    print()


def t9_forward_speed() -> None:
    per_season = ALL_LEAGUES
    p0, p1 = 0.50, 0.60
    n_need = ((Z95_ONE * math.sqrt(p0*(1-p0)) + 0.841621234 * math.sqrt(p1*(1-p1))) / (p1-p0)) ** 2
    print(f"Т9. Скорость детекции деградации (docs/05 разд. 3.8, docs/07 С14)")
    print(f"    падение 60%->50%, мощность 80%, уровень 5% -> нужно {n_need:.0f} наблюдений")
    print(f"{'доля матчей':>13}{'ставок/сезон':>14}{'сезонов до детекции':>22}")
    for rate in (0.05, 0.02, 0.01, 0.005):
        per = per_season * rate
        print(f"{rate:>12.1%}{per:>14.0f}{n_need/per:>22.1f}")
    print()


if __name__ == "__main__":
    for fn in (t1_breakeven_table, t2_one_sided, t3_per_window, t4_volume,
               t5_api_budget, t6_multiplicity, t7_mining_speed,
               t8_hypothesis_space, t9_forward_speed):
        fn()
