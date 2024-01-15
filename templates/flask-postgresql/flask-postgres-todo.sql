-- Adminer 4.8.0 PostgreSQL 11.11 dump

DROP TABLE IF EXISTS "todo";
DROP SEQUENCE IF EXISTS todo_id_seq;
CREATE SEQUENCE todo_id_seq INCREMENT 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1;

CREATE TABLE "public"."todo" (
    "id" integer DEFAULT nextval('todo_id_seq') NOT NULL,
    "title" character varying(100),
    "complete" boolean,
    CONSTRAINT "todo_pkey" PRIMARY KEY ("id")
) WITH (oids = false);

INSERT INTO "todo" ("title", "complete") VALUES
('計畫工讀生',	'1');

-- 2021-03-05 09:12:13.712878+00
