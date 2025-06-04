

def checkValidSemesterFormat(semester: str) -> bool:
    """
    Check if the semester format is valid.
    Valid formats are 'SSYY' or 'WSYY/YY', where:
    - 'SS' is the summer semester (e.g., 'SS23' for Summer 2023)
    - 'WS' is the winter semester (e.g., 'WS23/24' for Winter 2023/2024)
    - 'YY' is the last two digits of the year (e.g., '23' for 2023)
    """
    if len(semester) == 4 and semester[:2] in ['SS'] and semester[2:].isdigit():
        return True
    elif len(semester) == 7 and semester[:2] == 'WS' and semester[2:4].isdigit() and semester[5:7].isdigit() and semester[4] == '/':
        # Check if second yy is after first yy
        first_year = int(semester[2:4])
        second_year = int(semester[5:7])
        if first_year + 1 == second_year:
            return True
    return False