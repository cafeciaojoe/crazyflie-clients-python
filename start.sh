#!/bin/bash

# First get the current directory the script is run in.
readonly PROJECT_HOME="$(pwd)"
readonly INSTALL_MARKER=".install_cf_done"
# Concatenate the route to posenet and our virtual environment.
readonly POSENET="$PROJECT_HOME/src/poseParser/poser.py"
readonly POSEPARSER="$PROJECT_HOME/src/poseParser/parser.py"
readonly POSE_DEPS="$PROJECT_HOME/src/poseParser/requirements.txt"
readonly VIRTUAL_ENV_ACTIVATE="$PROJECT_HOME/venv/bin/activate"
# This will be the PID of the posenet program, for an easy kill later.
POSENET_PID=0
POSEPARSER_PID=0

# Kill the things
cleanup(){
  if [[ "$POSENET_PID" != 0 ]]; then
    kill "$POSENET_PID"
  fi

  if [[ "$POSEPARSER_PID" != 0 ]]; then
    kill "$POSEPARSER_PID"
  fi
}

# Runs the things.
run_the_things(){
  failstate=0

  source "$VIRTUAL_ENV_ACTIVATE"
  python3 "$POSENET" &
  POSENET_PID=$!

  if [[ $? != 0 ]]; then
    failstate=1
  fi

#  source "$VIRTUAL_ENV_ACTIVATE"
  python3 "$POSEPARSER" &
  POSEPARSER_PID=$!

  if [[ $? != 0 ]]; then
    failstate=1
  fi
  
  if [[ "$failstate" != 0 ]]; then
    return
  fi
  echo "Python server and backend launched"
  source "$VIRTUAL_ENV_ACTIVATE" && cfclient

  return $?
}

# Makes a python virtual env in current directory.
make_venv(){
  python3 -m venv "$PROJECT_HOME/venv"
  if [[ $? != 0 ]]; then
    exit 1
  fi
}

# Installs cf stuff with pip.
install_cf_deps(){
  source "$VIRTUAL_ENV_ACTIVATE"

  if [[ $? != 0 ]]; then
    exit 1
  fi

  source "$VIRTUAL_ENV_ACTIVATE" && pip install -e .
  if [[ $? != 0 ]]; then
    exit 1
  fi

  source "$VIRTUAL_ENV_ACTIVATE" && pip install -r "$POSE_DEPS"
  if [[ $? != 0 ]]; then
    exit 1
  fi

  touch "$PROJECT_HOME/$INSTALL_MARKER"
}

# Check for a venv, if missing, create one.
if ! [[ -d "$PROJECT_HOME/venv" ]]; then
  make_venv
  echo "make_venv called!"
fi

# Check if cfclient stuff has been installed
if ! [[ -f "$PROJECT_HOME/$INSTALL_MARKER" ]]; then
  install_cf_deps
  echo "Deps installed!"
fi

# Run all the things
run_the_things
# Kill the posenet
cleanup

exit 0
