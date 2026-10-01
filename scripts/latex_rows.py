# -*- coding: utf-8 -*-
r"""Splitting LaTeX on `\\` when only some of them end a row.

Four places counted row breaks by looking for `\\` and nothing else, and
all four were wrong in the same way. `\\` ends a row only at the top level
of the thing it is in; inside a brace group or a nested environment it is
an ordinary line break and ends nothing.

Measured, not supposed:

  * `\thead{Total \\ Time}` is one header cell holding a line break, and
    `table_cells` read it as two cells. `verify_tables` and `table_probe`
    split rows the same way, and that one is worse than a miscount: an
    agent translating that cell to a Korean phrase short enough for one
    line takes the row count from 2 to 1, and `verify_tables` refuses a
    CORRECT translation.
  * an `align` holding a `cases` counted three numbers where LaTeX prints
    two, and a `substack` did the same. Both are ordinary in a machine
    learning paper. Per K175 a miscount there is not local: every equation
    after it is off by the difference and every `\ref` into them lands on
    the wrong one.

Braces alone are not enough. A `cases` is opened by `\begin`, not by a
brace, so the depth that matters is both: brace depth for `\thead{a \\ b}`,
environment depth for `\begin{cases} a \\ b \end{cases}`.

The caller passes the INNER text -- what is between `\begin{tabular}` and
`\end{tabular}`, or between `\begin{align}` and `\end{align}`. Handing in
the wrapper too would open an environment on the first character and
suppress every split in the body.
"""
from __future__ import unicode_literals

import re

_COMMAND_RE = re.compile(r'\\([A-Za-z@]+)')


def split_rows(body):
    r"""`body` cut at every `\\` that actually ends a row.

    Always returns at least one piece, so `len(split_rows(x))` is the row
    count and matches what `re.split` gave for the flat case that was
    already right.
    """
    body = body or ''
    rows, brace, env, start, i, n = [], 0, 0, 0, 0, len(body)
    while i < n:
        ch = body[i]
        if ch != '\\':
            if ch == '{':
                brace += 1
            elif ch == '}':
                brace = max(0, brace - 1)
            i += 1
            continue
        if body[i + 1:i + 2] == '\\':
            if brace == 0 and env == 0:
                rows.append(body[start:i])
                start = i + 2
            i += 2
            continue
        m = _COMMAND_RE.match(body, i)
        if not m:
            # `\{`, `\}`, `\&`, `\%`, `\_`: an escaped character, and the
            # brace forms must not reach the depth counter above.
            i += 2
            continue
        i = m.end()
        if m.group(1) == 'begin':
            env += 1
        elif m.group(1) == 'end':
            env = max(0, env - 1)
    rows.append(body[start:])
    return rows


def nonempty_rows(body):
    """`split_rows` without the blank pieces a trailing `\\` leaves."""
    return [row for row in split_rows(body) if row.strip()]


def env_body(text, start, env):
    r"""What lies between `\begin{env}` at `start` and its own `\end{env}`.

    Nesting is counted, so an `align` holding another `align` closes on the
    right one. Returns the rest of the text when nothing closes it, which
    is what a truncated block should look like rather than an exception.
    """
    opener = re.compile(r'\\begin\s*\{%s\*?\}' % re.escape(env))
    closer = re.compile(r'\\end\s*\{%s\*?\}' % re.escape(env))
    depth, i = 1, start
    while i < len(text):
        close = closer.search(text, i)
        if not close:
            break
        following = opener.search(text, i)
        if following and following.start() < close.start():
            depth += 1
            i = following.end()
            continue
        depth -= 1
        if depth == 0:
            return text[start:close.start()]
        i = close.end()
    return text[start:]
