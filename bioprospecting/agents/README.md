# Agents

Checking agents, one per handover.

An agent reads the RO-Crate produced at the end of one phase and decides
whether the receiving phase can accept it. It checks the shape of the data,
meaning whether the required fields are present, and the semantics, meaning
whether those fields mean what the receiving phase expects them to mean.
