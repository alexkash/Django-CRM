CREATE DATABASE IF NOT EXISTS suitecrmdb CHARACTER SET utf8mb4;
USE suitecrmdb;
CREATE TABLE accounts (id varchar(36) PRIMARY KEY, amount decimal(24,6), nullable text, zero_date varchar(20), body text, blob_value blob, deleted tinyint DEFAULT 0);
INSERT INTO accounts VALUES ('001',123456789.123456,NULL,'0000-00-00','Київ\nПривіт',UNHEX('00FF'),0);
CREATE TABLE users (id varchar(36) PRIMARY KEY,user_name varchar(50),user_hash varchar(128),deleted tinyint DEFAULT 0);
INSERT INTO users VALUES ('1','fixture-admin','DO-NOT-EXPORT',0);
CREATE TABLE audit (value text);
INSERT INTO audit VALUES ('same'),('same');
