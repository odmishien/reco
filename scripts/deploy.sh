#!/bin/sh

# move to scripts directory
SCRIPT_DIR=`dirname $0`
cd $SCRIPT_DIR
cd ../

# copy resources to ec2
rsync -e "ssh -i ~/.ssh/reco.pem" --exclude '.*' -rltvz ./ ec2-user@18.176.126.121:/home/ec2-user

# start server
ssh -i ~/.ssh/reco.pem ec2-user@18.176.126.121 make run-with-build
