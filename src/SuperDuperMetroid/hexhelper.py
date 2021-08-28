class HexHelper:
    # Converts a hexadecimal string to a base 10 integer.
    @staticmethod
    def hexToInt(hexToConvert):
        return int(hexToConvert, 16)

    # Converts an integer to a hexadecimal string.
    @staticmethod
    def intToHex(intToConvert):
        return (hex(intToConvert)[2:]).upper()

    # Converts a hexadecimal string to binary data.
    @staticmethod
    def hexToData(hexToConvert):
        return bytes.fromhex(hexToConvert)

    # Converts binary data to a hexadecimal string.
    @staticmethod
    def dataToHex(dataToConvert):
        return "".join("{:02x}".format(x) for x in dataToConvert).upper()

    # Reverses the endianness of a hexadecimal string.
    @staticmethod
    def reverseEndianness(hexToReverse):
        assert (len(hexToReverse) % 2) == 0
        hexPairs = []
        for i in range(len(hexToReverse) // 2):
            hexPairs.append(hexToReverse[2 * i] + hexToReverse[2 * i + 1])
        reversedHexPairs = hexPairs[::-1]
        outputString = ""
        for pair in reversedHexPairs:
            outputString += pair
        return outputString

    # Pads a hexadecimal string with 0's until it meets the provided length.
    @staticmethod
    def padHex(hexToPad, numHexCharacters):
        returnHex = hexToPad
        while len(returnHex) < numHexCharacters:
            returnHex = "0" + returnHex
        return returnHex
