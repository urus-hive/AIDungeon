from story.utils import *
from other.cacher import *
import json


class Story():

    def __init__(self, story_start):

        self.story_start = story_start

        # list of actions. First action is the prompt length should always equal that of story blocks
        self.actions = []

        # list of story blocks first story block follows prompt and is intro story
        self.results = []

    def add_to_story(self, action, story_block):
        self.actions.append(action)
        self.results.append(story_block)

    def latest_result(self):
        if len(self.results) > 1:
            return self.results[-2] + self.actions[-1] + self.results[-1]
        elif len(self.results) == 1:
            return self.story_start + self.results[-1]
        else:
            return self.story_start

    def __str__(self):
        story_list = [self.story_start]
        for i in range(len(self.results)):
            story_list.append(self.actions[i])
            story_list.append(self.results[i])

        return "".join(story_list)


class StoryManager():

    def __init__(self, generator, story_prompt):
        self.generator = generator
        self.story_prompt = story_prompt

    def init_story(self):
        block = self.generator.generate(self.story_prompt)
        block = cut_trailing_sentence(block)
        block = story_replace(block)
        story_start = self.story_prompt + block
        self.story = Story(story_start)
        return story_start

    def story_context(self):
        return self.story.latest_result()


class UnconstrainedStoryManager(StoryManager):

    def __init__(self, generator, story_prompt):
        super().__init__(generator, story_prompt)
        self.init_story()

    def act(self, action_choice):
        result = self.generate_result(action_choice)
        self.story.add_to_story(action_choice, result)
        return result

    def generate_result(self, action):
        block = self.generator.generate(self.story_context() + action)
        block = cut_trailing_sentence(block)
        block = story_replace(block)
        return block


class ConstrainedStoryManager(StoryManager):

    def __init__(self, generator, story_prompt, action_verbs_key="classic"):
        super().__init__(generator, story_prompt)

        self.init_story()
        self.possible_action_results = None
        self.action_phrases = get_action_verbs(action_verbs_key)

    def get_possible_actions(self):
        if self.possible_action_results is None:
            self.possible_action_results = self.get_action_results()

        return [action_result[0] for action_result in self.possible_action_results]

    def act(self, action_choice_str):

        try:
            action_choice = int(action_choice_str)
        except:
            print("Error invalid choice.")
            return None, None

        if action_choice < 0 or action_choice >= len(self.action_phrases):
            print("Error invalid choice.")
            return None, None

        action, result = self.possible_action_results[action_choice]
        self.story.add_to_story(action, result)
        self.possible_action_results = self.get_action_results()
        return result, self.get_possible_actions()

    def get_action_results(self):
        return [self.generate_action_result(self.story_context(), phrase) for phrase in self.action_phrases]

    def generate_action_result(self, prompt, phrase, options=None):
        if options is None:
            options = {}

        action = phrase + " " + self.generator.generate(prompt + phrase, options)
        action_result = cut_trailing_sentence(action)

        action, result = split_first_sentence(action_result)
        result = story_replace(action_result)
        action = action_replace(action)

        return action, result


class CTRLStoryManager(ConstrainedStoryManager):
    def __init__(self, generator, story_prompt, action_verbs_key="classic"):
        super().__init__(generator, story_prompt)
        self.action_phrases = get_action_verbs("anything")

    def get_action_results(self):

        used_verbs = []
        results = []
        for phrase in self.action_phrases:
            options = {}
            options["used_verbs"] = used_verbs
            result = self.generate_action_result(self.story_context(), phrase, options=options)

            used_verb = result[0].split()[1]
            used_verbs.append(used_verb)

            results.append(result)
        return results


class CachedStoryManager(ConstrainedStoryManager):

    def __init__(self, generator, prompt_num, seed, credentials_file, action_verbs_key="classic", ):
        self.cacher = cacher(credentials_file)
        prompt = get_story_start("classic")
        super().__init__(generator, prompt, action_verbs_key)
        self.seed = seed
        self.prompt_num = prompt_num
        self.choices = []

        result = self.cacher.retrieve_from_cache(seed, prompt_num, [], "story")
        if result is not None:
            story_start = result
            self.story = Story(story_start)
        else:

            story_start = self.init_story()
            self.cacher.cache_file(seed, prompt_num, [], story_start, "story")

        self.possible_action_results = None

    def get_possible_actions(self):
        if self.possible_action_results is None:
            self.possible_action_results = self.get_action_results()

        return [action_result[0] for action_result in self.possible_action_results]

    def act(self, action_choice_str):

        try:
            action_choice = int(action_choice_str)
        except:
            print("Error invalid choice.")
            return None, None

        if action_choice < 0 or action_choice >= len(self.action_phrases):
            print("Error invalid choice.")
            return None, None

        self.choices.append(action_choice)
        action, result = self.possible_action_results[action_choice]
        self.story.add_to_story(action, result)
        self.possible_action_results = self.get_action_results()
        return result, self.get_possible_actions()

    def get_action_results(self):

        response = self.cacher.retrieve_from_cache(self.seed, self.prompt_num, self.choices, "choices")

        if response is not None:
            action_results = json.loads(response)
        else:
            print("Not found in cache. Generating...")
            action_results = super().get_action_results()
            response = json.dumps(action_results)
            self.cacher.cache_file(self.seed, self.prompt_num, self.choices, response, "choices")

        return action_results


