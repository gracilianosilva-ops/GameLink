import unittest

from servicos.game_activity_service import GameActivityService
from modelos.jogo import Jogo


class GameActivityServiceTests(unittest.TestCase):
    def test_build_index_matches_executable_to_game(self):
        jogo = Jogo(1, 'Elden Ring', 'RPG', 'FromSoftware', 2022)
        jogo.executavel = 'eldenring.exe'

        service = GameActivityService()
        index = service._build_process_index([jogo])

        self.assertIn('eldenring.exe', index)
        self.assertEqual(index['eldenring.exe'].titulo, 'Elden Ring')

    def test_build_index_creates_aliases_from_title(self):
        jogo = Jogo(2, 'The Witcher 3', 'RPG', 'CD Projekt', 2015)
        service = GameActivityService()
        index = service._build_process_index([jogo])

        self.assertIn('witcher3', index)
        self.assertEqual(index['witcher3'].titulo, 'The Witcher 3')


if __name__ == '__main__':
    unittest.main()

