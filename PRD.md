# LLM Cost Autopilot — Product Requirements

## Problem

Most tools send every task to one fixed model, usually the strongest one available. Nobody wants to guess wrong on a task that turns out hard, so the safe choice becomes the only choice. That means a one-line function takes as long as a gnarly bug fix, because both pay the price of the biggest model the system might ever need. Time spent scales with the ceiling, not the actual need.

## Solution

A routing layer sits between the caller and the model. It reads a coding task, picks the smallest model tier likely to succeed, runs the task, checks whether the result actually works, and only moves up to a bigger model if the small one fails. Across many tasks, the goal is the least total time spent that still gets every task done.

## Who this is for

The author's own coding-task workflow. A personal tool, not a product for other people, at least for now.

## Scope for v1

One task type: coding. A task arrives as a self-contained spec, such as a function or class description, with test cases attached. No existing codebase, no back-and-forth session. Groq handles the classification step; the three model tiers that do the actual work run on a local Ollama server, since this runs on the author's own machine.

## What "done right" means

A task passes when its code passes the tests submitted with it. That is the only judge: run the code, pass or fail. No model grades another model's work.

## What this actually optimizes

Originally framed as dollars: pick the cheapest model tier, spend the least money. That framing stopped fitting once the routed tiers moved to a local Ollama server (see architecture.md) — local inference has no metered cost, so a dollar figure reads $0 regardless of which tier ran, and there's nothing left to optimize in that unit.

What's real instead is **wall-clock time**. A 1B-parameter model answers in about a second; a 14B model can take many times longer for the same task. Running everything on the biggest model "just in case" wastes real time, even though it wastes no money. So the currency this system tracks is time, not dollars: not the fastest result on any single task, but the least total time spent across every task the system runs, even if a handful of individual tasks end up taking longer than a person guessing by hand would have.

The Groq classifier call is the one piece of this system that's still genuinely metered in dollars — that's tracked on its own (`ClassifierPrediction.cost_usd`) and isn't part of this time-based comparison.

## Non-goals for v1

- No routing across providers for the tiers doing the work — local Ollama models only, for now
- No reading or editing an existing codebase
- No multi-turn, tool-using sessions
- No container isolation for running code
- No support for tasks that ship without tests

## The cold-start problem

The classifier starts with no data on which tasks need which tier. Early tasks skip the classifier and run through the full staged cascade instead: smallest tier first, one step up on failure. Every run through that cascade becomes a labeled example — a real record of which tier a given task actually needed. Once enough examples exist, the classifier starts making the first guess instead of the system always starting at the bottom.

## Success metric

Total wall-clock time spent across a batch of tasks, measured against an estimate of what it would have taken running every task on the top model tier (see `app/models/timing.py` for how that estimate is derived, and its caveats — it's a placeholder pending more real measurements, the same spirit as any pricing table). This replaces the original dollar-based metric, which reads a meaningless flat $0 for the routed tiers now that they're local (see "What this actually optimizes" above).
