#!/usr/bin/env bash

set -Eeo pipefail

pre_run () {
  zenml integration install sklearn great_expectations
}

pre_run_forced () {
  zenml integration install sklearn great_expectations -f
}
