#!/bin/bash

# Usage: 
#   ./test.sh             -- to run all
#   ./test.sh test_toto   -- to only run test toto

ARG=''
if [ ! -z "$1" ]
then
  ARG="-k $1"
fi

poetry run ipython -c "import pytest; pytest.main(['.', '-x', '--pdb', '$ARG'])"
