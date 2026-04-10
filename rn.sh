#!/bin/bash

read -p "MSG: " msg

# generate random 5-character string
rand=$(tr -dc A-Za-z </dev/urandom | head -c 5)

git add .
git commit -m "$msg $rand"
git push origin main
