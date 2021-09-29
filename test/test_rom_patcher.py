from SuperDuperMetroid import ROM_Patcher

romSize = 3145728

# endAddress is excluded
def is_file_byte_range_empty(f, empty_byte, start_address, end_address):
    found_non_empty_byte = False
    f.seek(start_address)
    bytes = f.read(end_address - start_address)
    for byte in bytes:
        if byte != empty_byte[0]:
            print(byte)
            print(empty_byte)
            found_non_empty_byte = True
            break
    print(found_non_empty_byte)
    return not found_non_empty_byte


# Creates a blank file to test writes with
def create_blank_file(file_name, empty_byte):
    f = open(file_name, "wb+")
    f.write(b"\0" * romSize)
    f.seek(0)
    return f


# Converts a hexadecimal string to binary data.
def hex_to_data(hex_to_convert):
    return bytes.fromhex(hex_to_convert)


def test_gen_vanilla_game():
    result = ROM_Patcher.gen_vanilla_game()
    assert len(result) == 100


def test_add_starting_inventory():
    f = None
    try:
        file_name = "startingInventoryTest.bin"
        f = create_blank_file(file_name, b"\0")

        starting_items = [
            ROM_Patcher.PickupPlacementData(1, -1, "Morph Ball"),
            ROM_Patcher.PickupPlacementData(1, -1, "Gravity Suit"),
        ]
        item_get_routine_addresses_dict = {
            "Morph Ball": 0x1234,
            "Gravity Suit": 0x5678,
        }

        ROM_Patcher.add_starting_inventory(f, starting_items, item_get_routine_addresses_dict)

        # Assert the presence of routines
        assert is_file_byte_range_empty(f, b"\0", 0, 0x02FFFB)
        # function_to_return_properly
        assert not is_file_byte_range_empty(f, b"\0", 0x02FFFB, (0x02FFFB + 5))
        assert is_file_byte_range_empty(f, b"\0", (0x02FFFB + 5), 0x08763A)
        # award_starting_inventory_routine
        assert not is_file_byte_range_empty(f, b"\0", 0x08763A, (0x08763A + 43))
        assert is_file_byte_range_empty(f, b"\0", (0x08763A + 43), 0x1C0000)
        # Assert the presence of starting inventory data
        assert not is_file_byte_range_empty(f, b"\0", 0x1C0000, 0x1C0007)
        assert is_file_byte_range_empty(f, b"\0", 0x1C0007, romSize)

        # Assert correctness of routines
        function_to_return_properly = hex_to_data("A95FF6486B")
        award_starting_inventory_routine = hex_to_data(
            "AF0080B8AAE00000F020DAE220A99048C220A9FAFF48E220A98548C2208A0AAABF0080B8486BFACA80DB6B"
        )
        f.seek(0x02FFFB)
        return_function_bytes = f.read(5)
        f.seek(0x08763A)
        award_items_routine_bytes = f.read(43)

        assert function_to_return_properly == return_function_bytes
        assert award_starting_inventory_routine == award_items_routine_bytes

        # Assert the correctness of routine data
        f.seek(0x1C0000)
        starting_inventory_bytes = f.read(6)
        assert (bytearray(starting_inventory_bytes) == bytes([0x02, 0x00, 0x33, 0x12, 0x77, 0x56])) or (
            bytes(starting_inventory_bytes) == bytes([0x02, 0x00, 0x77, 0x56, 0x33, 0x12])
        )
    except Exception:
        f.close()
        raise


def test_write_save_initialization_routines_skip_intro():
    f = None
    try:
        file_name = "startSaveTest_SkipIntro.bin"
        f = create_blank_file(file_name, b"\0")

        ROM_Patcher.write_save_initialization_routines(f, True)

        # Assert the presence of routines
        assert is_file_byte_range_empty(f, b"\0", 0, 0x016EB4)
        assert not is_file_byte_range_empty(f, b"\0", 0x016EB4, (0x016EB4 + 70))
        assert is_file_byte_range_empty(f, b"\0", (0x016EB4 + 70), romSize)
        # Assert the correctness of routine data
        f.seek(0x016EB4)
        intro_and_ceres_default_start = hex_to_data(
            "9CE20DADDA09D01E223AF690A900008D9F07A900008D8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
        )
        start_save = f.read(70)
        assert intro_and_ceres_default_start == start_save
    except Exception:
        f.close()
        raise


def test_write_save_initialization_routines_custom_save_start():
    f = None
    try:
        file_name = "startSaveTest_CustomSaveStart.bin"
        f = create_blank_file(file_name, b"\0")

        ROM_Patcher.write_save_initialization_routines(f, True, ["Brinstar", 0])

        # Assert the presence of routines
        assert is_file_byte_range_empty(f, b"\0", 0, 0x016EB4)
        assert not is_file_byte_range_empty(f, b"\0", 0x016EB4, (0x016EB4 + 70))
        assert is_file_byte_range_empty(f, b"\0", (0x016EB4 + 70), romSize)
        # Assert the correctness of routine data
        f.seek(0x016EB4)
        custom_save_start = hex_to_data(
            "9CE20DADDA09D01E223AF690A901008D9F07A900008D8B07ADEA098F08D87EAD520922008081AD520922858081AF08D87E8DEA09228C8580A905008D9809AF18D97E8D500960"
        )
        start_save = f.read(70)
        assert custom_save_start == start_save
    except Exception:
        f.close()
        raise


def test_write_save_initialization_routines_with_intro_start_at_ceres():
    f = None
    try:
        file_name = "startSaveTest_IntroCeres.bin"
        f = create_blank_file(file_name, b"\0")

        ROM_Patcher.write_save_initialization_routines(f, False, ["Ceres Station", 0])

        # Assert the presence of routines
        assert is_file_byte_range_empty(f, b"\0", 0, 0x05C100)
        assert not is_file_byte_range_empty(f, b"\0", 0x05C100, (0x05C100 + 5))
        assert is_file_byte_range_empty(f, b"\0", (0x05C100 + 5), 0x096DF4)
        assert not is_file_byte_range_empty(f, b"\0", 0x096DF4, (0x096DF4 + 34))
        assert is_file_byte_range_empty(f, b"\0", (0x096DF4 + 34), romSize)
        # Assert the correctness of routine data
        f.seek(0x05C100)
        redirect_after_intro = hex_to_data("22F4ED9260")
        redirect_in_file = f.read(5)
        assert redirect_after_intro == redirect_in_file
        f.seek(0x096DF4)
        make_ceres_save = hex_to_data("A91F008F14D97E8D9809223AF690A906008D9F07A900008D8B07AD5209220080816B")
        start_save = f.read(34)
        assert make_ceres_save == start_save
    except Exception:
        f.close()
        raise


def test_write_crateria_wakeup_routine():
    f = None
    try:
        file_name = "crateriaWakeupTest.bin"
        f = create_blank_file(file_name, b"\0")

        ROM_Patcher.write_crateria_wakeup_routine(f)

        # Assert the presence of routines
        assert is_file_byte_range_empty(f, b"\0", 0, 0x07E652)
        assert not is_file_byte_range_empty(f, b"\0", 0x07E652, (0x07E652 + 19))
        assert is_file_byte_range_empty(f, b"\0", (0x07E652 + 19), romSize)
        # Assert the correctness of routine data
        f.seek(0x07E652)
        crateria_wakeup_routine = hex_to_data("AF73D87E290400F007BD0000AA4CE6E5E8E860")
        wakeup_bytes = f.read(19)
        assert crateria_wakeup_routine == wakeup_bytes
    except Exception:
        f.close()
        raise


def test_write_multiworld_routines():
    f = None
    try:
        file_name = "multiRoutineTest.bin"
        f = create_blank_file(file_name, b"\0")

        ROM_Patcher.write_multiworld_routines(f)

        # Assert the presence of routines
        assert is_file_byte_range_empty(f, b"\0", 0, 0x01AD66)
        assert not is_file_byte_range_empty(f, b"\0", 0x01AD66, (0x01AD66 + 22))
        assert is_file_byte_range_empty(f, b"\0", (0x01AD66 + 22), 0x087FF0)
        assert not is_file_byte_range_empty(f, b"\0", 0x087FF0, (0x087FF0 + 13))
        assert is_file_byte_range_empty(f, b"\0", (0x087FF0 + 13), romSize)
        # Assert the correctness of routine data
        f.seek(0x01AD66)
        item_get_routine = hex_to_data("AD1F1C22808085A900008F74FF7FAF80FF7F8D420A6B")
        item_get_bytes = f.read(22)
        f.seek(0x087FF0)
        execute_multiworld_routine = hex_to_data("E220A98348C220AF72FF7F486B")
        multi_exec_bytes = f.read(13)
        assert item_get_routine == item_get_bytes
        assert execute_multiworld_routine == multi_exec_bytes
    except Exception:
        f.close()
        raise
