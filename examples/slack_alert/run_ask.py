#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.

from pipelines.ask_pipeline import ask_pipeline
from steps.alerter_steps import alerter_ask_step
from steps.data_loader import data_loader
from steps.deployer import mlflow_model_deployer_step
from steps.evaluator import evaluator
from steps.formatter import test_acc_ask_formatter
from steps.trainer import svc_trainer_mlflow

if __name__ == "__main__":
    ask_pipeline(
        data_loader=data_loader(),
        trainer=svc_trainer_mlflow(),
        evaluator=evaluator(),
        formatter=test_acc_ask_formatter(),
        alerter=alerter_ask_step(),
        deployer=mlflow_model_deployer_step(),
    ).run()