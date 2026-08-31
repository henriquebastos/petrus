# Handler

A server-side callable implementation bound to a transition. A pure
handler projects firing effects locally; an impure handler
deterministically prepares one Petri-agnostic activity invocation,
then projects the frozen activity result into token and
delivery-registration effects.

Related: [Activity](activity.md),
[Derived Activity handler](derived-activity-handler.md)
