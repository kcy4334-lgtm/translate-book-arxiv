# -*- coding: utf-8 -*-
r"""The advisors have to stay consistent with each other and with SKILL.md.

Four of them arrived in two sittings, and the drift started immediately: one
gained a `kb.py` call without gaining `Bash`, and the section heading still
said how many there had been before. Both are silent failures — an agent
without the tool it is told to run fails at the first command, and a heading
that undercounts is how the newest advisor stops being called.

None of this needs a person to notice it, so it should not wait for one.
"""
import os
import re
import unittest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(SKILL_DIR, '.claude', 'agents')

COUNT_WORD = {1: 'One', 2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five',
              6: 'Six', 7: 'Seven', 8: 'Eight'}


def agent_files():
    if not os.path.isdir(AGENT_DIR):
        return []
    return sorted(f for f in os.listdir(AGENT_DIR) if f.endswith('.md'))


def read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def front_matter(text):
    m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if not m:
        return None, text
    fields = {}
    for line in m.group(1).split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            fields[key.strip()] = value.strip()
    return fields, text[m.end():]


class Definitions(unittest.TestCase):

    def test_there_is_at_least_one(self):
        self.assertTrue(agent_files(), 'no agent definitions found')

    def test_each_has_front_matter_with_name_and_description(self):
        for name in agent_files():
            fields, _body = front_matter(read(os.path.join(AGENT_DIR, name)))
            self.assertIsNotNone(fields, '%s: no front matter' % name)
            for key in ('name', 'description', 'tools'):
                self.assertIn(key, fields, '%s: no %s' % (name, key))
                self.assertTrue(fields[key], '%s: %s is empty' % (name, key))

    def test_the_name_matches_the_filename(self):
        for name in agent_files():
            fields, _body = front_matter(read(os.path.join(AGENT_DIR, name)))
            self.assertEqual(fields['name'], os.path.splitext(name)[0],
                             '%s: name does not match its filename' % name)

    def test_an_agent_told_to_run_a_script_has_bash(self):
        """Without it the agent fails at its first command, silently."""
        for name in agent_files():
            fields, body = front_matter(read(os.path.join(AGENT_DIR, name)))
            if re.search(r'python\s+scripts/\w+\.py', body):
                self.assertIn('Bash', fields['tools'],
                              '%s: runs a script and has no Bash' % name)

    def test_every_script_an_agent_names_exists(self):
        for name in agent_files():
            _fields, body = front_matter(read(os.path.join(AGENT_DIR, name)))
            for script in re.findall(r'python\s+(scripts/\w+\.py)', body):
                self.assertTrue(
                    os.path.isfile(os.path.join(SKILL_DIR, script)),
                    '%s: names %s, which does not exist' % (name, script))

    def test_none_of_them_claims_a_veto(self):
        """An advisor that can block is not an advisor; it is a gate."""
        for name in agent_files():
            _fields, body = front_matter(read(os.path.join(AGENT_DIR, name)))
            self.assertNotIn('you may block', body.lower(), name)


class SkillDocument(unittest.TestCase):

    def setUp(self):
        self.skill = read(os.path.join(SKILL_DIR, 'SKILL.md'))

    def test_the_heading_counts_the_advisors_that_exist(self):
        n = len(agent_files())
        self.assertIn('## %s advisors' % COUNT_WORD[n], self.skill,
                      'SKILL.md heading does not say there are %d' % n)

    def test_every_advisor_is_named_in_it(self):
        for name in agent_files():
            stem = os.path.splitext(name)[0]
            self.assertIn('`%s`' % stem, self.skill,
                          'SKILL.md never mentions %s' % stem)

    def test_each_one_says_when_to_call_it(self):
        for name in agent_files():
            stem = os.path.splitext(name)[0]
            head = re.search(r'(?m)^### `%s`.*$' % re.escape(stem), self.skill)
            self.assertIsNotNone(head, '%s has no section' % stem)
            self.assertIn('call it', head.group(0).lower(),
                          '%s: its heading does not say when to call it' % stem)


if __name__ == '__main__':
    unittest.main()
