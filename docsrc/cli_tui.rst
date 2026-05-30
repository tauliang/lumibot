CLI and TUI
===========

LumiBot includes a local operator command line and an optional Textual terminal
console. These tools run existing strategy scripts in child processes, so the
operator process stays separate from broker SDKs, strategy crashes, and signal
handling.

Install
-------

The core CLI is installed with LumiBot:

.. code-block:: bash

   pip install lumibot

The terminal UI is optional:

.. code-block:: bash

   pip install "lumibot[tui]"

Commands
--------

Open the operator console:

.. code-block:: bash

   lumibot tui

Run a backtest script and stream events:

.. code-block:: bash

   lumibot backtest \
     --script examples/my_strategy.py \
     --start 2025-01-01 \
     --end 2025-02-01 \
     --data-source none \
     --budget 100000

Run one live scheduled tick:

.. code-block:: bash

   lumibot run-live --script examples/my_strategy.py --once

Add ``--json`` to ``backtest`` or ``run-live`` to emit JSON lines for automation.

Runtime API
-----------

The programmatic API is available from ``lumibot.runtime``:

.. code-block:: python

   from pathlib import Path

   from lumibot.runtime import BacktestRunConfig, RunController

   config = BacktestRunConfig(
       script=Path("examples/my_strategy.py"),
       start="2025-01-01",
       end="2025-02-01",
       data_source="none",
       budget=100000,
   )

   handle = RunController().start(config)
   for event in handle.events():
       print(event.to_dict())

Events include run start, progress, log, order, position, artifact, agent trace,
finish, and failure records. Backtest progress is read from the existing
``logs/progress.csv`` file, and artifacts are discovered under ``logs/`` after
the child process exits.

Safety
------

The CLI/TUI redacts displayed configuration keys containing ``key``, ``token``,
``secret``, ``password``, or ``auth``. Avoid printing raw environment dictionaries
from custom operator integrations.
