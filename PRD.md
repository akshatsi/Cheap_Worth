# LLM Cost Autopilot — Product Requirements

## Problem

Most tools send every task to one fixed model, usually the strongest one available. Nobody wants to guess wrong on a task that turns out hard, so the safe choice becomes the only choice. That means a one-line function costs the same as a gnarly bug fix, because both pay the price of the hardest task the system might ever see. Spend scales with the ceiling, not the actual need.

## Solution

A routing layer sits between the caller and the model. It reads a coding task, picks the cheapest model tier likely to succeed, runs the task, checks whether the result actually works, and only moves up to a pricier model if the cheap one fails. Across many tasks, the goal is the smallest total spend that still gets every task done.

## Who this is for

The author's own coding-task workflow. A personal tool, not a product for other people, at least for now.

## Scope for v1

One task type: coding. A task arrives as a self-contained spec, such as a function or class description, with test cases attached. No existing codebase, no back-and-forth session, no provider besides Anthropic. Groq handles the classification step; Anthropic supplies the three model tiers that do the actual work.

## What "done right" means

A task passes when its code passes the tests submitted with it. That is the only judge: run the code, pass or fail. No model grades another model's work.

## What "cheapest" means

Not the lowest cost on any single task, but the lowest total spend across every task the system runs, even if a handful of individual tasks end up costing more than a person guessing by hand would have spent.

## Non-goals for v1

- No routing across providers other than Anthropic
- No reading or editing an existing codebase
- No multi-turn, tool-using sessions
- No container isolation for running code
- No support for tasks that ship without tests

## The cold-start problem

The classifier starts with no data on which tasks need which tier. Early tasks skip the classifier and run through the full staged cascade instead: cheapest tier first, one step up on failure. Every run through that cascade becomes a labeled example — a real record of which tier a given task actually needed. Once enough examples exist, the classifier starts making the first guess instead of the system always starting at the bottom.

## Success metric

Total dollars spent across a batch of tasks, measured against a baseline of running every task on the top model tier.
