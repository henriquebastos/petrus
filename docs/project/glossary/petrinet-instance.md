# Petrinet Instance

The formal durable execution of a `Net`: concrete tokens, current
marking, timers, activity lifecycle facts, and one canonical semantic
history, publicly named `petrus.impetus.instance.Instance`. Each
Instance is isolated with one history writer and coordinates with
other Instances by identified messaging, never shared marking or
history.

- Avoid: net instance
- Related: [Marking](marking.md), [History](history.md)
