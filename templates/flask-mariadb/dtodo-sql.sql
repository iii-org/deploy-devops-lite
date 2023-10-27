-- Adminer 4.8.0 MySQL 5.5.5-10.5.9-MariaDB dump

SET NAMES utf8;
SET time_zone = '+00:00';
SET foreign_key_checks = 0;
SET sql_mode = 'NO_AUTO_VALUE_ON_ZERO';

DROP TABLE IF EXISTS `todo`;
CREATE TABLE `todo` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `title` varchar(100) DEFAULT NULL,
  `complete` tinyint(1) DEFAULT NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `CONSTRAINT_1` CHECK (`complete` in (0,1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

INSERT INTO `todo` (`id`, `title`, `complete`) VALUES
(1,	'asdasda',	0),
(2,	'asdasdasd',	0),
(3,	'cccccccccccc',	0),
(4,	'eeeeeeeeeeeeee',	0),
(5,	'qqqqqqqqqqqqqqqqq',	0),
(6,	'aaaaaaaaaaaaaaaa',	0);

-- 2021-03-05 09:07:35
