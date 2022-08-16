#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Implementation of the Argo orchestrator."""

import base64
import subprocess
import sys
from typing import TYPE_CHECKING, Any, ClassVar, List, Optional, Tuple

import functools
from hera import Task, Workflow, WorkflowService

from kubernetes import config as k8s_config
from tfx.proto.orchestration.pipeline_pb2 import Pipeline as Pb2Pipeline
import errno
import os

from kubernetes import client, config
from zenml.enums import StackComponentType
from zenml.environment import Environment
from zenml.integrations.argo import ARGO_ORCHESTRATOR_FLAVOR
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.orchestrators import BaseOrchestrator
from zenml.stack import StackValidator
from zenml.utils import io_utils, networking_utils
from zenml.utils.pipeline_docker_image_builder import PipelineDockerImageBuilder
from zenml.integrations.argo.orchestrators.argo_entrypoint_configuration import ArgoEntrypointConfiguration

if TYPE_CHECKING:
    from zenml.pipelines.base_pipeline import BasePipeline
    from zenml.runtime_configuration import RuntimeConfiguration
    from zenml.stack import Stack
    from zenml.steps import BaseStep, ResourceConfiguration


logger = get_logger(__name__)

DEFAULT_ARGO_UI_PORT = 2746


def get_sa_token(service_account: str = "default", namespace: str = "default", config_file: Optional[str] = None):
    """Get ServiceAccount token using kubernetes config.
     Parameters
    ----------
    service_account: str
        The service account to authenticate from.
    namespace: str = 'default'
        The K8S namespace the workflow service submits workflows to. This defaults to the `default` namespace.
    config_file: Optional[str] = None
        The path to k8s configuration file.
     Raises
    ------
    FileNotFoundError
        When the config_file can not be found.
    """
    if config_file is not None and not os.path.isfile(config_file):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), config_file)

    config.load_kube_config(config_file=config_file)
    v1 = client.CoreV1Api()
    secret_name = v1.read_namespaced_service_account(service_account, namespace).secrets[0].name
    sec = v1.read_namespaced_secret(secret_name, namespace).data
    return base64.b64decode(sec["token"]).decode()


def dummy():
    print("dummy")

class ArgoOrchestrator(BaseOrchestrator, PipelineDockerImageBuilder):
    """Orchestrator responsible for running pipelines using Argo.

    Attributes:
        kubernetes_context: Name of a kubernetes context to run
            pipelines in.
        kubernetes_namespace: Name of the kubernetes namespace in which the
            pods that run the pipeline steps should be running.
        argo_ui_port: A local port to which the Argo UI will be forwarded.
        skip_ui_daemon_provisioning: If `True`, provisioning the Argo UI
            daemon will be skipped.
    """

    kubernetes_context: str
    kubernetes_namespace: str = "argo"
    argo_ui_port: int = DEFAULT_ARGO_UI_PORT
    skip_ui_daemon_provisioning: bool = False

    # Class Configuration
    FLAVOR: ClassVar[str] = ARGO_ORCHESTRATOR_FLAVOR

    def get_kubernetes_contexts(self) -> Tuple[List[str], Optional[str]]:
        """Get the list of configured Kubernetes contexts and the active context.

        Returns:
            A tuple containing the list of configured Kubernetes contexts and
            the active context.
        """
        try:
            contexts, active_context = k8s_config.list_kube_config_contexts()
        except k8s_config.config_exception.ConfigException:
            return [], None

        context_names = [c["name"] for c in contexts]
        active_context_name = active_context["name"]
        return context_names, active_context_name

    @property
    def validator(self) -> Optional[StackValidator]:
        """Ensures a stack with only remote components and a container registry.

        Returns:
            A `StackValidator` instance.
        """

        def _validate(stack: "Stack") -> Tuple[bool, str]:
            container_registry = stack.container_registry

            # should not happen, because the stack validation takes care of
            # this, but just in case
            assert container_registry is not None

            contexts, _ = self.get_kubernetes_contexts()

            if self.kubernetes_context not in contexts:
                return False, (
                    f"Could not find a Kubernetes context named "
                    f"'{self.kubernetes_context}' in the local Kubernetes "
                    f"configuration. Please make sure that the Kubernetes "
                    f"cluster is running and that the kubeconfig file is "
                    f"configured correctly. To list all configured "
                    f"contexts, run:\n\n"
                    f"  `kubectl config get-contexts`\n"
                )

            # go through all stack components and identify those that
            # advertise a local path where they persist information that
            # they need to be available when running pipelines.
            # for stack_comp in stack.components.values():
            #     local_path = stack_comp.local_path
            #     if not local_path:
            #         continue
            #     return False, (
            #         f"The Argo orchestrator is configured to run "
            #         f"pipelines in a remote Kubernetes cluster designated "
            #         f"by the '{self.kubernetes_context}' configuration "
            #         f"context, but the '{stack_comp.name}' "
            #         f"{stack_comp.TYPE.value} is a local stack component "
            #         f"and will not be available in the Argo pipeline "
            #         f"step.\nPlease ensure that you always use non-local "
            #         f"stack components with a Argo orchestrator, "
            #         f"otherwise you may run into pipeline execution "
            #         f"problems. You should use a flavor of "
            #         f"{stack_comp.TYPE.value} other than "
            #         f"'{stack_comp.FLAVOR}'."
            #     )
            #
            # if container_registry.is_local:
            #     return False, (
            #         f"The Argo orchestrator is configured to run "
            #         f"pipelines in a remote Kubernetes cluster designated "
            #         f"by the '{self.kubernetes_context}' configuration "
            #         f"context, but the '{container_registry.name}' "
            #         f"container registry URI '{container_registry.uri}' "
            #         f"points to a local container registry. Please ensure "
            #         f"that you always use non-local stack components with "
            #         f"a Argo orchestrator, otherwise you will "
            #         f"run into problems. You should use a flavor of "
            #         f"container registry other than "
            #         f"'{container_registry.FLAVOR}'."
            #     )

            return True, ""

        return StackValidator(
            required_components={StackComponentType.CONTAINER_REGISTRY},
            custom_validation_function=_validate,
        )

    def prepare_pipeline_deployment(
        self,
        pipeline: "BasePipeline",
        stack: "Stack",
        runtime_configuration: "RuntimeConfiguration",
    ) -> None:
        """Builds and pushes a Docker image for the current environment.

        Args:
            pipeline: The pipeline to be deployed.
            stack: The stack to be deployed.
            runtime_configuration: The runtime configuration to be used.
        """
        self.build_and_push_docker_image(
            pipeline_name=pipeline.name,
            docker_configuration=pipeline.docker_configuration,
            stack=stack,
            runtime_configuration=runtime_configuration,
        )

    def prepare_or_run_pipeline(
        self,
        sorted_steps: List["BaseStep"],
        pipeline: "BasePipeline",
        pb2_pipeline: Pb2Pipeline,
        stack: "Stack",
        runtime_configuration: "RuntimeConfiguration",
    ) -> Any:
        """Runs the pipeline on Argo.

        This function first compiles the ZenML pipeline into a Argo yaml
        and then applies this configuration to run the pipeline.

        Args:
            sorted_steps: A list of steps sorted by their order in the
                pipeline.
            pipeline: The pipeline object.
            pb2_pipeline: The pipeline object in protobuf format.
            stack: The stack object.
            runtime_configuration: The runtime configuration object.

        Raises:
            RuntimeError: If you try to run the pipelines in a notebook environment.
        """
        # First check whether the code running in a notebook
        if Environment.in_notebook():
            raise RuntimeError(
                "The Argo orchestrator cannot run pipelines in a notebook "
                "environment. The reason is that it is non-trivial to create "
                "a Docker image of a notebook. Please consider refactoring "
                "your notebook cells into separate scripts in a Python module "
                "and run the code outside of a notebook when using this "
                "orchestrator."
            )

        image_name = runtime_configuration["docker_image"]

        # Get a filepath to use to save the finished yaml to
        assert runtime_configuration.run_name

        # Dictionary mapping step names to airflow_operators. This will be needed
        # to configure airflow operator dependencies
        step_name_to_argo_task = {}

        with Workflow(pipeline.name, WorkflowService(host=f"https://127.0.0.1:{self.argo_ui_port}", token=get_sa_token(namespace=self.kubernetes_namespace), verify_ssl=False, namespace=self.kubernetes_namespace)) as w:
            for step in sorted_steps:
                # Create callable that will be used by argo to execute the step
                # within the orchestrated environment
                command = ArgoEntrypointConfiguration.get_entrypoint_command()
                arguments = (
                    ArgoEntrypointConfiguration.get_entrypoint_arguments(
                        step=step,
                        pb2_pipeline=pb2_pipeline,
                    )
                )

                current_task = Task(
                    step.name,
                    dummy,
                    image=image_name,
                    command=command,
                    args=arguments
                )

                if self.requires_resources_in_orchestration_environment(step):
                    logger.warning(
                        "Specifying step resources is not yet supported for "
                        "the Airflow orchestrator, ignoring resource "
                        "configuration for step %s.",
                        step.name,
                    )

                # Configure the current argo operator to run after all upstream
                # operators finished executing
                step_name_to_argo_task[step.name] = current_task
                upstream_step_names = self.get_upstream_step_names(
                    step=step, pb2_pipeline=pb2_pipeline
                )
                for upstream_step_name in upstream_step_names:
                    step_name_to_argo_task[upstream_step_name] >> current_task

        if runtime_configuration.schedule:
            logger.warning(
                "The Argo Orchestrator currently does not support the "
                "use of schedules. The `schedule` will be ignored "
                "and the pipeline will be run immediately."
            )

        logger.info(
            "Running Argo pipeline in kubernetes context '%s' and namespace "
            "'%s'.",
            self.kubernetes_context,
            self.kubernetes_namespace,
        )
        try:
            w.create()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to upload Argo pipeline: {str(e)}. "
                f"Please make sure your kubernetes config is present and the "
                f"{self.kubernetes_context} kubernetes context is configured "
                f"correctly.",
            )

    @property
    def root_directory(self) -> str:
        """Returns path to the root directory for all files concerning this orchestrator.

        Returns:
            Path to the root directory.
        """
        return os.path.join(
            io_utils.get_global_config_directory(),
            "argo",
            str(self.uuid),
        )

    @property
    def pipeline_directory(self) -> str:
        """Path to a directory in which the Argo pipeline files are stored.

        Returns:
            Path to the pipeline directory.
        """
        return os.path.join(self.root_directory, "pipelines")

    @property
    def _pid_file_path(self) -> str:
        """Returns path to the daemon PID file.

        Returns:
            Path to the daemon PID file.
        """
        return os.path.join(self.root_directory, "argo_daemon.pid")

    @property
    def log_file(self) -> str:
        """Path of the daemon log file.

        Returns:
            Path of the daemon log file.
        """
        return os.path.join(self.root_directory, "argo_daemon.log")

    @property
    def is_provisioned(self) -> bool:
        """Returns if a local k3d cluster for this orchestrator exists.

        Returns:
            True if a local k3d cluster exists, False otherwise.
        """
        return fileio.exists(self.root_directory)

    @property
    def is_running(self) -> bool:
        """Checks if the local UI daemon is running.

        Returns:
            True if the local UI daemon for this orchestrator is running.
        """
        if self.skip_ui_daemon_provisioning:
            return True

        if sys.platform != "win32":
            from zenml.utils.daemon import check_if_daemon_is_running

            return check_if_daemon_is_running(self._pid_file_path)
        else:
            return True

    def provision(self) -> None:
        """Provisions resources for the orchestrator."""
        fileio.makedirs(self.root_directory)

    def deprovision(self) -> None:
        """Deprovisions the orchestrator resources."""
        if self.is_running:
            self.suspend()

        if fileio.exists(self.log_file):
            fileio.remove(self.log_file)

    def resume(self) -> None:
        """Starts the UI forwarding daemon if necessary."""
        if self.is_running:
            logger.info("Argo UI forwarding is already running.")
            return

        self.start_ui_daemon()

    def suspend(self) -> None:
        """Stops the UI forwarding daemon if it's running."""
        if not self.is_running:
            logger.info("Argo UI forwarding not running.")
            return

        self.stop_ui_daemon()

    def start_ui_daemon(self) -> None:
        """Starts the UI forwarding daemon if possible."""
        port = self.argo_ui_port
        if (
            port == DEFAULT_ARGO_UI_PORT
            and not networking_utils.port_available(port)
        ):
            # if the user didn't specify a specific port and the default
            # port is occupied, fallback to a random open port
            port = networking_utils.find_available_port()

        command = [
            "kubectl",
            "--context",
            self.kubernetes_context,
            "--namespace",
            self.kubernetes_namespace,
            "port-forward",
            "svc/argo-server",
            f"{port}:2746",
        ]

        if not networking_utils.port_available(port):
            modified_command = command.copy()
            modified_command[-1] = "<PORT>:2746"
            logger.warning(
                "Unable to port-forward Argo UI to local port %d "
                "because the port is occupied. In order to access the Argo "
                "UI at http://localhost:<PORT>/, please run '%s' in a "
                "separate command line shell (replace <PORT> with a free port "
                "of your choice).",
                port,
                " ".join(modified_command),
            )
        elif sys.platform == "win32":
            logger.warning(
                "Daemon functionality not supported on Windows. "
                "In order to access the Argo UI at "
                "http://localhost:%d/, please run '%s' in a separate command "
                "line shell.",
                port,
                " ".join(command),
            )
        else:
            from zenml.utils import daemon

            def _daemon_function() -> None:
                """Port-forwards the Argo UI pod."""
                subprocess.check_call(command)

            daemon.run_as_daemon(
                _daemon_function,
                pid_file=self._pid_file_path,
                log_file=self.log_file,
            )
            logger.info(
                "Started Argo UI daemon (check the daemon logs at %s "
                "in case you're not able to view the UI). The Argo "
                "UI should now be accessible at http://localhost:%d/.",
                self.log_file,
                port,
            )

    def stop_ui_daemon(self) -> None:
        """Stops the UI forwarding daemon if it's running."""
        if fileio.exists(self._pid_file_path):
            if sys.platform == "win32":
                # Daemon functionality is not supported on Windows, so the PID
                # file won't exist. This if clause exists just for mypy to not
                # complain about missing functions
                pass
            else:
                from zenml.utils import daemon

                daemon.stop_daemon(self._pid_file_path)
                fileio.remove(self._pid_file_path)
                logger.info("Stopped Argo UI daemon.")