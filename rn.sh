#!/bin/bash

read -p "MSG: " msg

git add .
git commit -m '$msg'
git push origin main
