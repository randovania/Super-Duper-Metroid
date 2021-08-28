from SuperDuperMetroid import ROM_Patcher


def test_genVanillaGame():
    result = ROM_Patcher.genVanillaGame()
    assert len(result) == 100
