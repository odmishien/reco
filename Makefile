.PHONY: deploy
deploy:
	sh ./scripts/deploy.sh
.PHONY: run
run:
	docker-compose up

.PHONY: run-with-build
run-with-build:
	docker-compose up --build

.PHONY: stop
stop:
	docker-compose down
