# board_generator.py
from sudoku import Sudoku
from typing import List, Dict, Optional, Union
import random

def export_as_list(puzzle) -> List[List[Union[int, None]]]:
    """
    Экспортирует доску Sudoku в виде списка списков.
    """
    board = puzzle.board
    return [[cell if cell is not None else 0 for cell in row] for row in board]


def generate_sudoku_board(difficulty=0.1):
    """
    Возвращает случайно выбранную предгенерированную доску Sudoku с заданной сложностью.
    Каждая клетка представлена либо числом (предзаполненная клетка), либо 0 (пустая клетка).
    """
    # Каждый раз создается новый объект Sudoku
    random.seed()
    x = random.randint(0, 14112002)
    print(x)
    puzzle = Sudoku(3, seed=x).difficulty(difficulty)
    board = export_as_list(puzzle)
    return board
