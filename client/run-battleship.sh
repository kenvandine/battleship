#!/bin/bash

SERVER_URL=$(snapctl get server-url)

export SERVER_URL

$SNAP/bin/battleship "$@"
