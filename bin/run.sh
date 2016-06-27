#!/bin/bash

export PYTHONPATH=/root/hyperagent

screen python /root/hyperagent/hyperagent/agent/hyper_agent.py --config-file=/etc/hyperagent/hyper-agent.conf 

