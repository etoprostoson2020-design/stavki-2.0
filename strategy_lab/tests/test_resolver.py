"""Фаза 2: Entity Resolution. Алиасы склеиваются, разные клубы — нет."""
from fsl.canonical.resolver import TeamResolver


def test_alias_merges_to_same_team(sess):
    r = TeamResolver(sess)
    a = r.resolve("Ath Madrid")
    assert a.canonical_name == "Atletico Madrid"


def test_similar_names_are_not_merged(sess):
    """'Ath Madrid' и 'Ath Bilbao' похожи строкой, но это разные клубы."""
    r = TeamResolver(sess)
    madrid = r.resolve("Ath Madrid")
    bilbao = r.resolve("Ath Bilbao")
    assert madrid.id != bilbao.id
    assert {madrid.canonical_name, bilbao.canonical_name} == {"Atletico Madrid",
                                                              "Athletic Bilbao"}


def test_resolution_is_stable(sess):
    r = TeamResolver(sess)
    assert r.resolve("Espanol").id == r.resolve("Espanol").id
    assert r.resolve("Espanol").canonical_name == "Espanyol"


def test_unknown_team_is_registered_not_guessed(sess):
    """Неизвестное название заводится как новая команда, а не подгоняется к похожей."""
    r = TeamResolver(sess)
    new = r.resolve("Some New Club")
    assert new.canonical_name == "Some New Club"
    assert new.id != r.resolve("Sevilla").id
