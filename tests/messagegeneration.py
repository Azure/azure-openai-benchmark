import unittest

from benchmark.messagegeneration import RandomMessagesGenerator


class TestRandomMessageGeneraor(unittest.TestCase):
    def test_init(self):
        generator = RandomMessagesGenerator(
            model="gpt-3.5-turbo-0613", tokens=123, max_tokens=456
        )
        # Check message content and token count
        self.assertEqual(len(generator._cached_messages_and_tokens[0], 2))
        self.assertEqual(len(generator._cached_messages_and_tokens[0], 2))

    def test_generate_messages(self):
        generator = RandomMessagesGenerator(
            model="gpt-3.5-turbo-0613", tokens=123, max_tokens=456
        )
        messages, tokens = generator.generate_messages()
        # Check message content and token count
        self.assertEqual(len(messages), 2)
        self.assertEqual(tokens, 123)
