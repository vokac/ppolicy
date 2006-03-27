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
GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,DROP
  ON ppolicy.* TO 'ppolicy'@'localhost'
  IDENTIFIED BY 'secret';

--
-- Apply new (user) privileges (do I need this?)
--
FLUSH PRIVILEGES;
