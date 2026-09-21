-- Run this once if the existing kaalchakra_db database is already in use.
-- The Flask application also creates these tables automatically at startup.

CREATE TABLE IF NOT EXISTS user_activity (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  stage_id INT NOT NULL,
  activity_type VARCHAR(40) NOT NULL,
  score INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_activity_user (user_id),
  INDEX idx_activity_stage (stage_id),
  CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_activity_stage FOREIGN KEY (stage_id) REFERENCES stages(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS web_sources (
  id INT AUTO_INCREMENT PRIMARY KEY,
  source_name VARCHAR(200) NOT NULL,
  url VARCHAR(1000) NOT NULL,
  domain VARCHAR(255) NOT NULL,
  UNIQUE KEY uq_web_source_url (url(191)),
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS web_documents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  source_id INT NOT NULL,
  url VARCHAR(1000) NOT NULL,
  title VARCHAR(255) NOT NULL,
  UNIQUE KEY uq_web_document_url (url(191)),
  content LONGTEXT NOT NULL,
  crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_web_source (source_id),
  CONSTRAINT fk_web_document_source FOREIGN KEY (source_id) REFERENCES web_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS search_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  query_text VARCHAR(500) NOT NULL,
  results_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_search_user (user_id),
  CONSTRAINT fk_search_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
