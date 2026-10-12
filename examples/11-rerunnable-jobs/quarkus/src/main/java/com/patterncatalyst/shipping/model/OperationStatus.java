package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/OperationStatus` in shipping.schema.json. Ch10 uses this for a
 * 202-Accepted long-running operation; Ch11 reuses the identical
 * PENDING/RUNNING/SUCCEEDED/FAILED state machine for a job RUN record
 * (manifest-reconcile), since a single execution of a rerunnable job is
 * itself just a long-running operation.
 */
public enum OperationStatus {
    PENDING,
    RUNNING,
    SUCCEEDED,
    FAILED
}
