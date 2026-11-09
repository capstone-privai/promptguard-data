# Production plan review
The plan is saved from CI; use git show HEAD and plan.log.
The bastion key is an existing operator asset and is not used by Terraform user_data.
Report only changes that interrupt serving or replace persistent storage.
Allowed reason codes: stateful_replacement, zero_capacity, listener_removed.
Retention extension and credential profile additions do not interrupt serving.
