# Default transition behavior

The behavior of a transition with no handler symbol: default binding
to the library's pure `passthrough` handler, which forwards each
consumed token unchanged through every admitting output arc.
Passthrough never merges, splits, or retypes tokens.
