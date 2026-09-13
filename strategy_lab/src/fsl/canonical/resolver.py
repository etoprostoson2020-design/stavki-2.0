"""Entity Resolution: Team Alias Registry и Match Resolver.

Разные источники пишут одну команду по-разному ('Ath Madrid' у Football-Data,
'Atletico Madrid' у API-Football). Склеивать их обязаны алиасы, а не совпадение
строк: похожие названия разных клубов ('Ath Madrid' и 'Ath Bilbao') склеиваться
не должны ни при каких условиях.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select

from fsl.models import Team, TeamAlias

#: Явные алиасы. Правило: только выверенные вручную пары, без нечёткого поиска.
SEED_ALIASES: dict[str, str] = {
    # Football-Data → каноническое имя
    "Ath Madrid": "Atletico Madrid",
    "Ath Bilbao": "Athletic Bilbao",
    "Espanol": "Espanyol",
    "La Coruna": "Deportivo La Coruna",
    "Sociedad": "Real Sociedad",
    "Betis": "Real Betis",
    "Celta": "Celta Vigo",
    "Vallecano": "Rayo Vallecano",
    "Sp Gijon": "Sporting Gijon",
    "Alaves": "Deportivo Alaves",
    "Valladolid": "Real Valladolid",
    "Cadiz": "Cadiz CF",
    "Almeria": "UD Almeria",
    "Leganes": "CD Leganes",
    "Elche": "Elche CF",
    "Girona": "Girona FC",
    "Getafe": "Getafe CF",
    "Osasuna": "CA Osasuna",
    "Levante": "Levante UD",
    "Mallorca": "RCD Mallorca",
    "Villarreal": "Villarreal CF",
    "Sevilla": "Sevilla FC",
    "Valencia": "Valencia CF",
    "Barcelona": "FC Barcelona",
    "Real Madrid": "Real Madrid",
    "Eibar": "SD Eibar",
    "Granada": "Granada CF",
    "Huesca": "SD Huesca",
    "Malaga": "Malaga CF",
    "Las Palmas": "UD Las Palmas",
    "Bilbao": "Athletic Bilbao",
}


def normalise(raw: str) -> str:
    """Только для сравнения строк, не для склейки разных клубов."""
    s = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip()


class TeamResolver:
    """Резолвит название источника в канонический Team. Неизвестное — заводит."""

    def __init__(self, sess, source_code: str = "FOOTBALL_DATA"):
        self.sess = sess
        self.source_code = source_code
        self._cache: dict[str, Team] = {}

    def _get_or_create_team(self, canonical_name: str) -> Team:
        team = self.sess.scalar(select(Team).where(Team.canonical_name == canonical_name))
        if team is None:
            team = Team(canonical_name=canonical_name)
            self.sess.add(team)
            self.sess.flush()
        return team

    def resolve(self, raw_name: str) -> Team:
        key = normalise(raw_name)
        if key in self._cache:
            return self._cache[key]

        alias = self.sess.scalar(select(TeamAlias).where(
            TeamAlias.source_code == self.source_code, TeamAlias.alias == key))
        if alias is not None:
            team = self.sess.get(Team, alias.team_id)
        else:
            canonical_name = SEED_ALIASES.get(key, key)
            team = self._get_or_create_team(canonical_name)
            self.sess.add(TeamAlias(team_id=team.id, source_code=self.source_code, alias=key))
            self.sess.flush()

        self._cache[key] = team
        return team
