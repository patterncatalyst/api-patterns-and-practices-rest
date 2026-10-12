package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.JobDefinition;
import com.patterncatalyst.shipping.model.Operation;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

/**
 * Ch11 rerunnable-jobs: a single, singleton job named {@code
 * manifest-reconcile}, split into configure (schedule, server-owned) and
 * execute (run records) resources:
 *
 * <ul>
 *   <li>{@code PUT /jobs/manifest-reconcile} — configure/enable the
 *       schedule. 201 the first time, 200 thereafter.</li>
 *   <li>{@code GET /jobs/manifest-reconcile} — read the schedule. 404 if
 *       never configured.</li>
 *   <li>{@code POST /jobs/manifest-reconcile/runs} — "run now": an on-demand
 *       execution, independent of the scheduler. 202 + a run record.</li>
 *   <li>{@code GET /jobs/manifest-reconcile/runs} — list run records,
 *       newest first.</li>
 *   <li>{@code GET /jobs/manifest-reconcile/runs/{runId}} — read one run
 *       record.</li>
 * </ul>
 *
 * The server's own scheduler (see {@link JobStore#configure}) also produces
 * run records automatically, at the configured interval, while the job is
 * enabled — a client configures *when*; it never has to drive each
 * execution itself.
 */
@Path("/jobs/" + JobStore.JOB_ID)
public class JobResource {

    @Inject
    JobStore store;

    public record JobDefinitionRequest(Boolean enabled, Integer intervalSeconds) {
    }

    @PUT
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response configure(JobDefinitionRequest request) {
        if (request == null || request.enabled() == null
                || request.intervalSeconds() == null || request.intervalSeconds() < 1) {
            return problem(400, "Invalid job definition",
                    "enabled (boolean) and intervalSeconds (integer >= 1) are required");
        }
        JobStore.ConfigureResult result = store.configure(request.enabled(), request.intervalSeconds());
        Response.Status status = result.created() ? Response.Status.CREATED : Response.Status.OK;
        return Response.status(status).entity(result.definition()).build();
    }

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response get() {
        JobDefinition definition = store.getDefinition();
        if (definition == null) {
            return jobNotConfigured();
        }
        return Response.ok(definition).build();
    }

    @POST
    @Path("/runs")
    @Produces(MediaType.APPLICATION_JSON)
    public Response triggerRun() {
        Operation run = store.triggerRun();
        if (run == null) {
            return jobNotConfigured();
        }
        return Response.status(Response.Status.ACCEPTED)
                .header("Location", "/jobs/" + JobStore.JOB_ID + "/runs/" + run.id())
                .entity(run)
                .build();
    }

    @GET
    @Path("/runs")
    @Produces(MediaType.APPLICATION_JSON)
    public Response listRuns() {
        if (store.getDefinition() == null) {
            return jobNotConfigured();
        }
        return Response.ok(store.listRuns()).build();
    }

    @GET
    @Path("/runs/{runId}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getRun(@PathParam("runId") String runId) {
        Operation run = store.getRun(runId);
        if (run == null) {
            return problem(404, "Run not found", "No run with id " + runId);
        }
        return Response.ok(run).build();
    }

    private Response jobNotConfigured() {
        return problem(404, "Job not configured",
                "No job definition exists for " + JobStore.JOB_ID
                        + "; PUT /jobs/" + JobStore.JOB_ID + " first");
    }

    private Response problem(int status, String title, String detail) {
        Problem problem = new Problem(title, status, detail);
        return Response.status(status).type("application/problem+json").entity(problem).build();
    }
}
