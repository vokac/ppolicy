--
-- Create new ppolicy database
--
CREATE DATABASE IF NOT EXISTS ppolicy;

--
-- Create new user that will be used to access database
-- You should change password 'secret' to something more secure
-- If you are using MySQL running on some different machine
-- than replace 'localhost' with appropriate domain name or '%'
--
GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,DROP,LOCK TABLES
  ON ppolicy.* TO 'ppolicy'@'localhost'
  IDENTIFIED BY 'secret';
-- GRANT SELECT,LOCK TABLES
--  ON ppolicy.* TO 'ppolicy'@'%'
--  IDENTIFIED BY 'secret';

--
-- Apply new (user) privileges (do I need this?)
--
FLUSH PRIVILEGES;

-- table for synchronizaction changes from master DB
--CREATE TABLE `changes` (
--  `date` datetime NOT NULL DEFAULT '0000-00-00 00:00:00'
--) ENGINE=MyISAM DEFAULT CHARSET=latin1;
