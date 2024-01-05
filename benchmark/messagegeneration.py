# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import copy
import json
import logging
import math
import random
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple

import wonderwords

from benchmark.oaitokenizer import num_tokens_from_messages


class BaseMessagesGenerator(ABC):
    """
    Base class for message generators.
    :param model: Model being used in testing.
    :param prevent_server_caching: When True, random characters will be added to
        the start of each message to prevent server-side caching.
    """

    def __init__(self, model: str, prevent_server_caching: bool):
        self.model = model
        self.prevent_server_caching = prevent_server_caching

    @abstractmethod
    def generate_messages(self) -> List[Dict[str, str]]:
        """
        Generate `messages` array.
        Returns Tuple of messages array and actual context token count.
        """
        pass

    def add_anticache_prefix(
        self, messages: Dict[str, str], messages_tokens: int
    ) -> Tuple[Dict[str, str], int]:
        """
        Add a prefix to the each message in messages to prevent any server-side
        caching.
        Returns a modified copy of messages and an updated token count.
        """
        messages = copy.deepcopy(messages)
        for message in messages:
            message["content"] = str(time.time()) + " " + message["content"]
            # Timestamps strings like "1704441942.868042 " use 8 tokens for OpenAI GPT models. Update token count
            messages_tokens += 8
        return (messages, messages_tokens)

    def remove_anticache_prefix(
        self, messages: Dict[str, str], messages_tokens: int
    ) -> Tuple[Dict[str, str], int]:
        """
        Remove the anticache prefix from each message in messages.
        Returns a modified copy of messages and an updated token count.
        """
        messages = copy.copy(messages)
        for message in messages:
            message["content"] = " ".join(message["content"].split()[1:])
            # Recalculate token count
        messages_tokens = num_tokens_from_messages(messages, self.model)
        return (messages, messages_tokens)


class RandomMessagesGenerator(BaseMessagesGenerator):
    """
    Generates context messages asking for a story to be written, with a set of
    random english words in order to ensure the context window is `max_tokens`
    long.
    :param model: Model being used in testing.
    :param prevent_server_caching: When True, random characters will be added to
        the start of each message to prevent server-side caching.
    :param tokens: Number of context tokens to use.
    :param max_tokens: Number of requested max_tokens.
    """

    _cached_messages_and_tokens: List[Tuple[Dict[str, str], int]] = []

    def __init__(
        self,
        model: str,
        prevent_server_caching: bool,
        tokens: int,
        max_tokens: int = None,
    ):
        super().__init__(model, prevent_server_caching)
        logging.info("warming up prompt cache")
        r = wonderwords.RandomWord()
        messages = [{"role": "user", "content": ""}]
        if max_tokens is not None:
            messages.append(
                {
                    "role": "user",
                    "content": f"write a long essay about life in at least {max_tokens} tokens",
                }
            )
        messages_tokens = num_tokens_from_messages(messages, model)
        if self.prevent_server_caching:
            # Add anticache prefix before we start generating random words to ensure
            # token count when used in testing is correct
            messages, messages_tokens = self.add_anticache_prefix(
                messages, messages_tokens
            )
        prompt = ""
        base_prompt = messages[0]["content"]
        while True:
            messages_tokens = num_tokens_from_messages(messages, model)
            remaining_tokens = tokens - messages_tokens
            if remaining_tokens <= 0:
                break
            prompt += (
                " ".join(r.random_words(amount=math.ceil(remaining_tokens / 4))) + " "
            )
            messages[0]["content"] = base_prompt + prompt

        if self.prevent_server_caching:
            # Now remove the anticache prefix from both messages
            messages, messages_tokens = self.remove_anticache_prefix(
                messages, messages_tokens
            )
        self._cached_messages_and_tokens = [(messages, messages_tokens)]

    def generate_messages(self) -> Tuple[Dict[str, str], int]:
        """
        Generate `messages` array.
        Returns Tuple of messages array and actual context token count.
        """
        messages, messages_tokens = self._cached_messages_and_tokens[0]
        if self.prevent_server_caching:
            return self.add_anticache_prefix(messages, messages_tokens)
        return (messages, messages_tokens)


class ReplayMessagesGenerator(BaseMessagesGenerator):
    """
    Generates context messages based on an existing JSON file, sampling randomly.
    :param model: Model being used in testing.
    :param prevent_server_caching: When True, random characters will be added to
        the start of each message to prevent server-side caching.
    :param path: Number of context tokens to use.
    """

    _cached_messages_and_tokens: List[Tuple[Dict[str, str], int]] = []

    def __init__(self, model: str, prevent_server_caching: bool, path: str):
        super().__init__(model, prevent_server_caching)
        # Load messages from file, checking structure
        logging.info("loading messages from file")
        try:
            with open(path, "r") as f:
                all_messages_lists = json.load(f)
        except Exception as e:
            raise ValueError(f"error loading replay file: {e}")
        if not isinstance(all_messages_lists, list):
            raise ValueError(
                "replay file must contain a JSON array. see README.md for more details."
            )
        if len(all_messages_lists) == 0:
            raise ValueError(
                "replay file must contain at least one list of messages. see README.md for more details."
            )
        if not isinstance(all_messages_lists, list) and all(
            isinstance(messages, list) and len(messages) > 0
            for messages in all_messages_lists
        ):
            raise ValueError(
                "replay file must contain a list of valid messages lists. see README.md for more details."
            )
        # Get num tokens for each message list
        for messages in all_messages_lists:
            messages_tokens = num_tokens_from_messages(messages, model)
            self._cached_messages_and_tokens.append((messages, messages_tokens))

    def generate_messages(self) -> Tuple[Dict[str, str], int]:
        """
        Generate `messages` array.
        Returns Tuple of messages array and actual context token count.
        """
        messages, messages_tokens = random.sample(
            self._cached_messages_and_tokens, k=1
        )[0]
        if self.prevent_server_caching:
            return self.add_anticache_prefix(messages, messages_tokens)
        return (messages, messages_tokens)
