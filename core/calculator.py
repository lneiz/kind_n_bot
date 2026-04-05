from datetime import date
from typing import Dict, List

def reduce_to_arcana(n: int) -> int:
    """Reduces a number to the range 1-22 for the Matrix of Destiny."""
    while n > 22:
        n = sum(int(d) for d in str(n))
    return n

def get_pythagoras_square(birth_date: date) -> Dict[int, int]:
    """Calculates the Pythagoras square digits count."""
    day = birth_date.day
    month = birth_date.month
    year = birth_date.year
    
    # 1. Sum of all digits in birth date
    digits_str = f"{day:02d}{month:02d}{year}"
    d1 = sum(int(d) for d in digits_str)
    
    # 2. Sum of digits of d1
    d2 = sum(int(d) for d in str(d1))
    
    # 3. d1 - 2 * first digit of day
    first_digit_of_day = int(str(day).zfill(2)[0])
    if first_digit_of_day == 0: # handle single digit days like 05
         first_digit_of_day = int(str(day).zfill(2)[1]) if day < 10 else int(str(day)[0])
    
    # Actually, the rule for the first digit of the day in Pythagoras square 
    # is usually the first non-zero digit of the day.
    day_str = str(day).zfill(2)
    first_non_zero_digit = int(day_str[0]) if day_str[0] != '0' else int(day_str[1])
    
    d3 = d1 - 2 * first_non_zero_digit
    
    # 4. Sum of digits of d3
    d4 = sum(int(d) for d in str(d3))
    
    # Collect all digits
    all_digits = digits_str + str(d1) + str(d2) + str(d3) + str(d4)
    
    counts = {i: 0 for i in range(1, 10)}
    for char in all_digits:
        if char.isdigit() and char != '0':
            digit = int(char)
            if digit in counts:
                counts[digit] += 1
                
    return counts

def get_matrix_destiny_central(birth_date: date) -> int:
    """Calculates the central arcana of the Matrix of Destiny."""
    day = reduce_to_arcana(birth_date.day)
    month = reduce_to_arcana(birth_date.month)
    year = reduce_to_arcana(birth_date.year)
    
    # The central arcana is the sum of the four outer arcanas (top, right, bottom, left)
    # Day (left), Month (top), Year (right), and the fourth is the sum of these three (bottom)
    bottom = reduce_to_arcana(day + month + year)
    
    central = reduce_to_arcana(day + month + year + bottom)
    return central

def calculate_all(birth_date: date) -> Dict:
    """Returns all calculations for AI interpretation."""
    return {
        "pythagoras": get_pythagoras_square(birth_date),
        "matrix_destiny_central": get_matrix_destiny_central(birth_date)
    }
